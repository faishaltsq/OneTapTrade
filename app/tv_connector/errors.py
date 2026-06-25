class TVConnectionError(Exception):
    pass


class TVNotRunningError(TVConnectionError):
    pass


class TVToolError(TVConnectionError):
    pass


class TVMCPProcessError(TVConnectionError):
    pass
