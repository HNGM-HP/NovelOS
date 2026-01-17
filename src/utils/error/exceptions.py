"""
自定义异常类和错误分类函数
"""

import re
import traceback
from typing import Optional, Any, Dict, Tuple

from .codes import ErrorCode, ErrorCategory, get_error_description


class VibeCodingError(Exception):
    """
    VibeCoding统一异常基类

    Attributes:
        code: 6位错误码
        message: 错误消息
        original_error: 原始异常
        context: 错误上下文信息
    """

    def __init__(
        self,
        code: int,
        message: str = "",
        original_error: Optional[BaseException] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message or get_error_description(code)
        self.original_error = original_error
        self.context = context or {}

        super().__init__(self.message)

    @property
    def category(self) -> ErrorCategory:
        """获取错误大类"""
        category = self.code // 100000
        try:
            return ErrorCategory(category)
        except ValueError:
            return ErrorCategory.UNKNOWN_ERROR

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "code": self.code,
            "message": self.message,
            "category": self.category.name,
            "context": self.context,
            "original_error": str(self.original_error) if self.original_error else None,
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def __repr__(self) -> str:
        return f"VibeCodingError(code={self.code}, message={self.message!r})"


def classify_error(error: BaseException, context: Optional[Dict[str, Any]] = None) -> VibeCodingError:
    """
    将原始异常分类为VibeCodingError

    Args:
        error: 原始异常
        context: 额外的上下文信息

    Returns:
        VibeCodingError: 分类后的错误
    """
    # 如果已经是 VibeCodingError，直接返回（避免重复分类）
    if isinstance(error, VibeCodingError):
        # 可以更新 context 信息
        if context:
            error.context.update(context)
        return error

    error_str = str(error)
    error_type = type(error).__name__
    ctx = context or {}

    # 记录原始错误信息
    ctx["original_type"] = error_type
    ctx["original_message"] = error_str

    code, message = _classify_by_type_and_message(error_type, error_str, error)

    return VibeCodingError(
        code=code,
        message=message,
        original_error=error,
        context=ctx,
    )


def _classify_by_type_and_message(
    error_type: str, error_str: str, error: BaseException
) -> Tuple[int, str]:
    """
    根据错误类型和消息分类错误

    Returns:
        (error_code, error_message)
    """

    # ==================== AttributeError ====================
    if error_type == "AttributeError":
        return _classify_attribute_error(error_str)

    # ==================== TypeError ====================
    if error_type == "TypeError":
        return _classify_type_error(error_str)

    # ==================== ValidationError (Pydantic) ====================
    if "ValidationError" in error_type:
        return _classify_validation_error(error_str)

    # ==================== ValueError ====================
    if error_type == "ValueError":
        return _classify_value_error(error_str)

    # ==================== KeyError ====================
    if error_type == "KeyError":
        return ErrorCode.CODE_KEY_NOT_FOUND, f"键不存在: {error_str}"

    # ==================== IndexError ====================
    if error_type == "IndexError":
        return ErrorCode.CODE_INDEX_OUT_OF_RANGE, f"索引越界: {error_str}"

    # ==================== NameError ====================
    if error_type == "NameError":
        return ErrorCode.CODE_NAME_NOT_DEFINED, f"名称未定义: {error_str}"

    # ==================== ImportError / ModuleNotFoundError ====================
    if error_type in ("ImportError", "ModuleNotFoundError"):
        error_lower = error_str.lower()
        # 特定的导入错误可能与环境配置有关
        if any(lib in error_lower for lib in ["numpy", "moviepy", "cv2", "opencv", "PIL", "pillow", "torch", "tensorflow"]):
            return ErrorCode.CONFIG_ENV_INVALID, f"依赖库配置错误: {error_str}"
        # cannot import name 类型的错误
        if "cannot import name" in error_lower:
            return ErrorCode.CONFIG_ENV_INVALID, f"依赖库版本不兼容: {error_str}"
        return ErrorCode.CODE_NAME_IMPORT_ERROR, f"模块导入错误: {error_str}"

    # ==================== SyntaxError ====================
    if error_type == "SyntaxError":
        return ErrorCode.CODE_SYNTAX_INVALID, f"语法错误: {error_str}"

    # ==================== IndentationError ====================
    if error_type == "IndentationError":
        return ErrorCode.CODE_SYNTAX_INDENTATION, f"缩进错误: {error_str}"

    # ==================== NotImplementedError ====================
    if error_type == "NotImplementedError":
        if "async" in error_str.lower() or "awrap" in error_str.lower():
            return ErrorCode.RUNTIME_ASYNC_NOT_IMPL, f"异步方法未实现: {error_str}"
        return ErrorCode.RUNTIME_EXECUTION_FAILED, f"功能未实现: {error_str}"

    # ==================== TimeoutError ====================
    if error_type in ("TimeoutError", "asyncio.TimeoutError"):
        if "subprocess" in error_str.lower():
            return ErrorCode.RUNTIME_SUBPROCESS_TIMEOUT, f"子进程执行超时: {error_str}"
        if "requests" in error_str.lower():
            return ErrorCode.API_NETWORK_TIMEOUT, f"请求超时: {error_str}"
        return ErrorCode.RUNTIME_TIMEOUT, f"执行超时: {error_str}"

    # ==================== RuntimeError ====================
    if error_type == "RuntimeError":
        return _classify_runtime_error(error_str)

    # ==================== API相关错误 ====================
    if "APIError" in error_type or "openai" in error_type.lower():
        return _classify_api_error(error_str)

    # ==================== 网络相关错误 ====================
    if error_type in ("ConnectionError", "ConnectionRefusedError", "ConnectionResetError"):
        return ErrorCode.API_NETWORK_CONNECTION, f"网络连接错误: {error_str}"

    # ==================== 文件相关错误 ====================
    if error_type == "FileNotFoundError":
        return ErrorCode.RESOURCE_FILE_NOT_FOUND, f"文件不存在: {error_str}"

    if error_type in ("IOError", "OSError"):
        return _classify_io_error(error_str)

    # ==================== 内存错误 ====================
    if error_type == "MemoryError":
        return ErrorCode.RUNTIME_MEMORY_ERROR, f"内存不足: {error_str}"

    # ==================== 递归错误 ====================
    if error_type == "RecursionError":
        return ErrorCode.RUNTIME_RECURSION_LIMIT, f"递归深度超限: {error_str}"

    # ==================== CancelledError ====================
    if "CancelledError" in error_type:
        return ErrorCode.RUNTIME_CANCELLED, "执行被取消"

    # ==================== UnboundLocalError ====================
    if error_type == "UnboundLocalError":
        return ErrorCode.CODE_NAME_NOT_DEFINED, f"局部变量未定义: {error_str}"

    # ==================== ConnectionError / TimeoutError ====================
    if error_type in ("ConnectionError", "ConnectTimeoutError", "NewConnectionError"):
        return ErrorCode.API_NETWORK_CONNECTION, f"网络连接错误: {error_str}"

    if error_type in ("TimeoutError", "ReadTimeoutError"):
        return ErrorCode.API_NETWORK_TIMEOUT, f"网络超时: {error_str}"

    # ==================== GraphRecursionError (LangGraph) ====================
    if "RecursionError" in error_type or "GraphRecursionError" in error_type:
        return ErrorCode.RUNTIME_RECURSION_LIMIT, f"递归深度超限: {error_str}"

    # ==================== InvalidUpdateError (LangGraph) ====================
    if "InvalidUpdateError" in error_type:
        return ErrorCode.BUSINESS_NODE_FAILED, f"状态更新无效: {error_str}"

    # ==================== JSONDecodeError ====================
    if error_type == "JSONDecodeError":
        return ErrorCode.VALIDATION_JSON_DECODE, f"JSON解析错误: {error_str}"

    # ==================== HTTPError ====================
    if error_type == "HTTPError":
        return ErrorCode.API_NETWORK_HTTP_ERROR, f"HTTP请求错误: {error_str}"

    # ==================== OSError ====================
    if error_type == "OSError":
        return _classify_io_error(error_str)

    # ==================== requests异常 ====================
    if "requests" in error_type.lower() or "MissingSchema" in error_type or "InvalidSchema" in error_type:
        return _classify_requests_error(error_str)

    # ==================== subprocess异常 ====================
    if "subprocess" in error_type.lower() or "TimeoutExpired" in error_type:
        return ErrorCode.RUNTIME_SUBPROCESS_TIMEOUT, f"子进程执行超时: {error_str}"

    # ==================== greenlet异常 ====================
    if "greenlet" in error_type.lower():
        return ErrorCode.RUNTIME_THREAD_ERROR, f"线程切换错误: {error_str}"

    # ==================== cv2/OpenCV异常 ====================
    if "cv2" in error_type.lower():
        return ErrorCode.RESOURCE_IMAGE_PROCESS_FAILED, f"图像处理错误: {error_str}"

    # ==================== botocore/S3异常 ====================
    if "botocore" in error_type.lower() or "NoSuchBucket" in error_type:
        return ErrorCode.RESOURCE_S3_UPLOAD_FAILED, f"S3存储错误: {error_str}"

    # ==================== Exception (自定义业务异常) ====================
    if error_type == "Exception":
        # 检查是否是包装的其他类型错误
        if "ValidationError" in error_str:
            return _classify_validation_error(error_str)
        if "APIError" in error_str:
            return _classify_api_error(error_str)
        if "InvalidUpdateError" in error_str:
            return ErrorCode.BUSINESS_NODE_FAILED, f"节点返回值无效: {error_str[:200]}"
        return _classify_custom_exception(error_str)

    # ==================== 未知错误 ====================
    return ErrorCode.UNKNOWN_EXCEPTION, f"({error_type}): {error_str}"


def _classify_attribute_error(error_str: str) -> Tuple[int, str]:
    """分类 AttributeError"""
    error_lower = error_str.lower()

    # 常见的 model_dump 错误 (Pydantic对象误用)
    if "model_dump" in error_lower:
        return ErrorCode.CODE_ATTR_MODEL_DUMP, f"对象类型错误，不是Pydantic模型: {error_str}"

    # 方法不存在的提示
    if "did you mean" in error_lower:
        return ErrorCode.CODE_ATTR_METHOD_NOT_FOUND, f"方法名错误: {error_str}"

    # 'str' object has no attribute
    if "'str' object" in error_str:
        return ErrorCode.CODE_ATTR_WRONG_TYPE, f"字符串类型错误: {error_str}"

    # 'NoneType' object has no attribute
    if "'nonetype' object" in error_lower:
        return ErrorCode.CODE_ATTR_WRONG_TYPE, f"对象为None: {error_str}"

    # 通用属性不存在
    return ErrorCode.CODE_ATTR_NOT_FOUND, f"属性不存在: {error_str}"


def _classify_type_error(error_str: str) -> Tuple[int, str]:
    """分类 TypeError"""
    error_lower = error_str.lower()

    # 缺少必需参数
    if "missing" in error_lower and ("required" in error_lower or "argument" in error_lower):
        return ErrorCode.CODE_TYPE_MISSING_ARG, f"缺少必需参数: {error_str}"

    # 多余参数
    if "takes" in error_lower and ("positional argument" in error_lower or "got" in error_lower):
        return ErrorCode.CODE_TYPE_EXTRA_ARG, f"参数数量错误: {error_str}"

    # 不可调用
    if "not callable" in error_lower:
        return ErrorCode.CODE_TYPE_NOT_CALLABLE, f"对象不可调用: {error_str}"

    # 不可迭代
    if "not iterable" in error_lower:
        return ErrorCode.CODE_TYPE_NOT_ITERABLE, f"对象不可迭代: {error_str}"

    # 不可下标访问
    if "not subscriptable" in error_lower:
        return ErrorCode.CODE_TYPE_NOT_SUBSCRIPTABLE, f"对象不支持下标访问: {error_str}"

    return ErrorCode.CODE_TYPE_WRONG_ARG, f"类型错误: {error_str}"


def _classify_validation_error(error_str: str) -> Tuple[int, str]:
    """分类 Pydantic ValidationError"""
    error_lower = error_str.lower()

    # 必填字段缺失
    if "field required" in error_lower or "missing" in error_lower:
        # 提取字段名
        field_match = re.search(r"for (\w+Input|\w+State)\s*\n(\w+)", error_str)
        if field_match:
            field_name = field_match.group(2)
            return ErrorCode.VALIDATION_FIELD_REQUIRED, f"必填字段缺失: {field_name}"
        return ErrorCode.VALIDATION_FIELD_REQUIRED, f"必填字段缺失: {error_str[:200]}"

    # 类型错误
    if "type_error" in error_lower or "input should be" in error_lower:
        return ErrorCode.VALIDATION_FIELD_TYPE, f"字段类型错误: {error_str[:200]}"

    # 值错误 (如日期格式)
    if "value_error" in error_lower or "value error" in error_lower:
        if "日期" in error_str or "date" in error_lower:
            return ErrorCode.VALIDATION_FIELD_FORMAT, f"日期格式错误: {error_str[:200]}"
        return ErrorCode.VALIDATION_FIELD_VALUE, f"字段值错误: {error_str[:200]}"

    return ErrorCode.VALIDATION_FIELD_CONSTRAINT, f"验证失败: {error_str[:200]}"


def _classify_value_error(error_str: str) -> Tuple[int, str]:
    """分类 ValueError"""
    error_lower = error_str.lower()

    # 人脸检测相关
    if "人脸" in error_str or "face" in error_lower:
        return ErrorCode.RESOURCE_FACE_NOT_DETECTED, error_str

    return ErrorCode.VALIDATION_FIELD_VALUE, f"值错误: {error_str}"


def _classify_runtime_error(error_str: str) -> Tuple[int, str]:
    """分类 RuntimeError"""
    error_lower = error_str.lower()

    # 飞书相关
    if "飞书" in error_str or "feishu" in error_lower:
        return ErrorCode.INTEGRATION_FEISHU_API_FAILED, error_str

    # 微信相关
    if "微信" in error_str or "wechat" in error_lower:
        return ErrorCode.INTEGRATION_WECHAT_API_FAILED, error_str

    return ErrorCode.RUNTIME_EXECUTION_FAILED, f"运行时错误: {error_str}"


def _classify_api_error(error_str: str) -> Tuple[int, str]:
    """分类 API 相关错误"""
    error_lower = error_str.lower()

    # 资源点不足 (优先检查) - 归类到业务错误
    if "资源点不足" in error_str or "errbalanceoverdue" in error_lower:
        return ErrorCode.BUSINESS_QUOTA_INSUFFICIENT, f"资源点不足: {error_str[:200]}"

    # 图片格式不支持
    if "image format" in error_lower or "image_url" in error_lower:
        return ErrorCode.API_LLM_IMAGE_FORMAT, f"图片格式不支持: {error_str[:200]}"

    # 视频相关
    if "video" in error_lower:
        if "404" in error_str:
            return ErrorCode.API_VIDEO_GEN_NOT_FOUND, f"视频生成服务不可用: {error_str[:200]}"
        return ErrorCode.API_VIDEO_GEN_FAILED, f"视频生成失败: {error_str[:200]}"

    # 速率限制
    if "rate limit" in error_lower or "too many requests" in error_lower:
        return ErrorCode.API_LLM_RATE_LIMIT, f"请求频率超限: {error_str[:200]}"

    # Token超限
    if "token" in error_lower and ("limit" in error_lower or "exceed" in error_lower):
        return ErrorCode.API_LLM_TOKEN_LIMIT, f"Token超限: {error_str[:200]}"

    # 认证错误
    if "auth" in error_lower or "unauthorized" in error_lower or "401" in error_str:
        return ErrorCode.API_LLM_AUTH_FAILED, f"API认证失败: {error_str[:200]}"

    # 无效请求
    if "invalid" in error_lower:
        return ErrorCode.API_LLM_INVALID_REQUEST, f"API请求无效: {error_str[:200]}"

    return ErrorCode.API_LLM_REQUEST_FAILED, f"API请求失败: {error_str[:200]}"


def _classify_io_error(error_str: str) -> Tuple[int, str]:
    """分类 IO 错误"""
    error_lower = error_str.lower()

    if "no such file" in error_lower:
        return ErrorCode.RESOURCE_FILE_NOT_FOUND, f"文件不存在: {error_str}"

    if "permission denied" in error_lower:
        return ErrorCode.RESOURCE_FILE_READ_ERROR, f"文件权限错误: {error_str}"

    return ErrorCode.RESOURCE_FILE_READ_ERROR, f"文件读取错误: {error_str}"


def _classify_requests_error(error_str: str) -> Tuple[int, str]:
    """分类 requests 库相关错误"""
    error_lower = error_str.lower()

    # URL格式错误 (MissingSchema, InvalidSchema)
    if "missingschema" in error_lower or "no scheme supplied" in error_lower:
        return ErrorCode.API_NETWORK_URL_INVALID, f"URL格式无效，缺少协议头: {error_str[:200]}"

    if "invalidschema" in error_lower or "no connection adapters" in error_lower:
        return ErrorCode.API_NETWORK_URL_INVALID, f"URL格式无效: {error_str[:200]}"

    # 连接超时
    if "connecttimeout" in error_lower or "connect timeout" in error_lower:
        return ErrorCode.API_NETWORK_TIMEOUT, f"连接超时: {error_str[:200]}"

    # 读取超时
    if "readtimeout" in error_lower or "read timeout" in error_lower:
        return ErrorCode.API_NETWORK_TIMEOUT, f"读取超时: {error_str[:200]}"

    # 连接错误
    if "connectionerror" in error_lower or "max retries exceeded" in error_lower:
        return ErrorCode.API_NETWORK_CONNECTION, f"连接失败: {error_str[:200]}"

    # SSL错误
    if "sslerror" in error_lower or "ssl" in error_lower and "error" in error_lower:
        return ErrorCode.API_NETWORK_SSL_ERROR, f"SSL证书错误: {error_str[:200]}"

    return ErrorCode.API_NETWORK_HTTP_ERROR, f"HTTP请求错误: {error_str[:200]}"


def _classify_custom_exception(error_str: str) -> Tuple[int, str]:
    """分类自定义 Exception"""
    error_lower = error_str.lower()

    # 资源点不足 (优先级最高，因为这是常见错误) - 归类到业务错误
    if "资源点不足" in error_str or "errbalanceoverdue" in error_lower:
        return ErrorCode.BUSINESS_QUOTA_INSUFFICIENT, f"资源点不足: {error_str[:200]}"

    # 余额/配额相关 - 归类到业务错误
    if "余额" in error_str or "balance" in error_lower:
        if "不足" in error_str or "insufficient" in error_lower or "overdue" in error_lower:
            return ErrorCode.BUSINESS_BALANCE_OVERDUE, f"余额不足: {error_str[:200]}"

    if "配额" in error_str or "quota" in error_lower:
        if "超" in error_str or "exceed" in error_lower:
            return ErrorCode.BUSINESS_QUOTA_EXCEEDED, f"配额超限: {error_str[:200]}"
        return ErrorCode.BUSINESS_QUOTA_INSUFFICIENT, f"配额不足: {error_str[:200]}"

    # 视频生成配置相关
    if "视频生成需要配置" in error_str or "api key" in error_lower:
        return ErrorCode.CONFIG_API_KEY_MISSING, error_str[:500]

    # 图片生成
    if "图片生成" in error_str or "image gen" in error_lower:
        return ErrorCode.API_IMAGE_GEN_FAILED, error_str[:200]

    # 视频生成
    if "视频生成" in error_str or "video gen" in error_lower:
        return ErrorCode.API_VIDEO_GEN_FAILED, error_str[:200]

    # 音频相关
    if "音频" in error_str or "audio" in error_lower:
        return ErrorCode.RESOURCE_AUDIO_PROCESS_FAILED, error_str[:200]

    # 微信相关
    if "微信" in error_str or "wechat" in error_lower:
        if "access_token" in error_lower:
            return ErrorCode.INTEGRATION_WECHAT_AUTH_FAILED, error_str[:500]
        return ErrorCode.INTEGRATION_WECHAT_API_FAILED, error_str[:200]

    # 飞书相关
    if "飞书" in error_str or "feishu" in error_lower:
        return ErrorCode.INTEGRATION_FEISHU_API_FAILED, error_str[:200]

    # S3/存储相关
    if "s3" in error_lower or "upload" in error_lower or "download" in error_lower:
        if "url" in error_lower or "presigned" in error_lower:
            return ErrorCode.RESOURCE_S3_URL_FAILED, error_str[:200]
        return ErrorCode.RESOURCE_S3_UPLOAD_FAILED, error_str[:200]

    # 生肖内容生成 (从日志中发现的常见错误)
    if "生肖" in error_str:
        return ErrorCode.BUSINESS_NODE_FAILED, error_str[:200]

    # 通用业务失败
    if "失败" in error_str or "failed" in error_lower:
        return ErrorCode.BUSINESS_NODE_FAILED, error_str[:200]

    return ErrorCode.UNKNOWN_ERROR, error_str[:200]
