def identity(room, authorization):
    return (room, authorization.removeprefix("Bearer ") if authorization else None)
