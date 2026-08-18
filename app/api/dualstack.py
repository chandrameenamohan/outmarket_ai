"""One socket that answers on IPv6 and IPv4 both.

Split out of `server.py` only because that file is at its 400-line ceiling; it is
one class and it belongs conceptually beside the server it serves.
"""

from __future__ import annotations

import socket
from http.server import ThreadingHTTPServer


class DualStackServer(ThreadingHTTPServer):
    """Listen on IPv6 AND IPv4, because a private network may offer only one of them.

    `ThreadingHTTPServer` inherits `address_family = AF_INET`, so the default binds v4
    only. Railway's private network resolves `<service>.railway.internal` to a AAAA
    record and nothing else, so a v4-only socket is unreachable from the web service —
    the failure is a connection refused at first render, not at boot, which is the
    expensive kind to diagnose. Binding `::` with V6ONLY off accepts both families on
    one socket, so localhost and compose keep working unchanged.

    ponytail: no fallback if the host has IPv6 compiled out. Docker, Railway and macOS
    all have it; a host that does not would need the AF_INET path back.
    """

    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()
