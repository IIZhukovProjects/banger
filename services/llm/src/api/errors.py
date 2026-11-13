from fastapi.responses import JSONResponse


def error(code, message, status, retryable=False):
    return JSONResponse(
        {"code": code, "message": message, "retryable": retryable}, status_code=status
    )
