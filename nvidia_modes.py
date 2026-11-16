"""NVIDIA custom modes through the driver's public NVAPI interface.

ABI definitions follow NVIDIA/nvapi 51e5aae (nvapi.h and CustomTiming.cpp).
Only the installed System32 driver DLL is loaded; no NVIDIA binary is bundled.
See THIRD_PARTY_LICENSES/NVIDIA-NVAPI.txt and docs/NVIDIA.md.
"""
import ctypes as C
import os

U32, U16, U8, F32 = C.c_uint32, C.c_uint16, C.c_uint8, C.c_float


class TimingExtra(C.Structure):
    _fields_ = [('flag', U32), ('rr', U16), ('rrx1k', U32), ('aspect', U32),
                ('rep', U16), ('status', U32), ('name', U8 * 40)]


class Timing(C.Structure):
    _fields_ = [('HVisible', U16), ('HBorder', U16), ('HFrontPorch', U16),
                ('HSyncWidth', U16), ('HTotal', U16), ('HSyncPol', U8),
                ('VVisible', U16), ('VBorder', U16), ('VFrontPorch', U16),
                ('VSyncWidth', U16), ('VTotal', U16), ('VSyncPol', U8),
                ('interlaced', U16), ('pclk', U32), ('etc', TimingExtra)]


class TimingFlags(C.Structure):
    # The anonymous bitfield union occupies a separate 32-bit storage unit.
    _fields_ = [('interlaced_reserved', U32), ('format_id', U32), ('scaling', U32)]


class TimingInput(C.Structure):
    _fields_ = [('version', U32), ('width', U32), ('height', U32), ('rr', F32),
                ('flag', TimingFlags), ('type', C.c_int32)]


class Viewport(C.Structure):
    _fields_ = [('x', F32), ('y', F32), ('w', F32), ('h', F32)]


class CustomDisplay(C.Structure):
    _fields_ = [('version', U32), ('width', U32), ('height', U32), ('depth', U32),
                ('colorFormat', C.c_int32), ('srcPartition', Viewport),
                ('xRatio', F32), ('yRatio', F32), ('timing', Timing), ('hwModeSetOnly', U32)]


class NvidiaError(Exception):
    def __init__(self, operation, code=None, detail=''):
        self.code = code
        message = f'NVIDIA {operation}失败'
        if code is not None:
            message += f'（错误码 {code}）'
        if code in (-3, -104, -208):
            message += '：当前驱动或显示连接不支持创建自定义分辨率。'
        elif code == -175:
            message += '：需要管理员权限。'
        elif detail:
            message += '：' + detail
        super().__init__(message)


IDS = {'initialize': 0x0150E828, 'unload': 0xD22BDD7E,
       'display_id': 0xAE457190, 'timing': 0x175167E9,
       'try_mode': 0x1F7DB630, 'save_mode': 0x49882876, 'revert': 0xCBBD40F0}


class NvidiaApi:
    def __init__(self):
        path = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'nvapi64.dll')
        if C.sizeof(C.c_void_p) != 8 or not os.path.isfile(path):
            raise NvidiaError('初始化', detail='未找到 64 位 NVIDIA 驱动。非 NVIDIA 连接的显示器需要已存在的分辨率。')
        try:
            self.dll = C.CDLL(path)
            self.query = self.dll.nvapi_QueryInterface
            self.query.argtypes, self.query.restype = [U32], C.c_void_p
            self.functions = {}
            self.call('initialize', [])
        except NvidiaError:
            raise
        except OSError as exc:
            raise NvidiaError('初始化', detail='无法加载已安装的 NVIDIA 驱动。') from exc

    def function(self, key, arguments):
        if key not in self.functions:
            address = self.query(IDS[key])
            if not address:
                raise NvidiaError('接口查询', detail='当前驱动未提供所需接口，请更新 NVIDIA 驱动。')
            self.functions[key] = C.CFUNCTYPE(C.c_int32, *arguments)(address)
        return self.functions[key]

    def call(self, key, arguments, *values):
        code = self.function(key, arguments)(*values)
        if code != 0:
            raise NvidiaError({'initialize': '初始化', 'display_id': '主显示器识别',
                               'timing': '时序计算', 'try_mode': '分辨率测试',
                               'save_mode': '保存自定义分辨率', 'revert': '恢复测试前显示模式'}.get(key, key), code)

    def display_id(self, device_name):
        result = U32()
        self.call('display_id', [C.c_char_p, C.POINTER(U32)], device_name.encode('ascii'), C.byref(result))
        return result.value

    def timing(self, display_id, width=0, height=0, refresh=0, kind=0):
        request = TimingInput()
        request.version = C.sizeof(request) | (1 << 16)
        request.width, request.height, request.rr, request.type = width, height, refresh, kind
        request.flag.scaling = 1 if kind != 0 else 0
        result = Timing()
        self.call('timing', [U32, C.POINTER(TimingInput), C.POINTER(Timing)], display_id, C.byref(request), C.byref(result))
        return result

    def close(self):
        try:
            self.call('unload', [])
        except NvidiaError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def create_custom_resolution(device_name, width, height, refresh):
    """Trial, save, and always revert the trial before the caller changes devices."""
    if not (type(width) is int and type(height) is int and 200 <= width <= 16384
            and 200 <= height <= 16384 and 20 <= refresh <= 1000):
        raise ValueError('自定义分辨率或刷新率超出支持范围。')
    with NvidiaApi() as api:
        display_id = api.display_id(device_name)
        current = api.timing(display_id)
        exact_refresh = current.etc.rrx1k / 1000 if current.etc.rrx1k else refresh
        custom = CustomDisplay()
        custom.version = C.sizeof(custom) | (1 << 16)
        custom.width, custom.height, custom.depth, custom.colorFormat = width, height, 32, 21
        custom.srcPartition = Viewport(0, 0, 1, 1)
        custom.xRatio = custom.yRatio = 1
        # Same calculation and scaling flag as NVIDIA's official CustomTiming sample.
        custom.timing = api.timing(display_id, width, height, exact_refresh, kind=6)
        ids = (U32 * 1)(display_id)
        primary_error = None
        try:
            api.call('try_mode', [C.POINTER(U32), U32, C.POINTER(CustomDisplay)], ids, 1, C.byref(custom))
            api.call('save_mode', [C.POINTER(U32), U32, U32, U32], ids, 1, 1, 1)
        except Exception as exc:
            primary_error = exc
            raise
        finally:
            # A failed trial may still have partially changed the hardware configuration.
            try:
                api.call('revert', [C.POINTER(U32), U32], ids, 1)
            except NvidiaError:
                if primary_error is None:
                    raise
        return {'width': width, 'height': height, 'refresh': exact_refresh, 'display_id': display_id}
