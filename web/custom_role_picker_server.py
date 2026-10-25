"""Lifecycle and loopback binding for the custom-role picker HTTP surface."""
from __future__ import annotations

import ipaddress
import logging
from typing import Any

from aiohttp import web

import config

custom_role_picker_logger = logging.getLogger("web.custom_role_picker_server")


def loopback_bind_host(value: str) -> str | None:
    """Accept only literal loopback IP addresses for internal web listeners."""
    candidate = str(value).strip()
    if candidate.lower() == "localhost":
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return address.compressed if address.is_loopback else None


class CustomRolePickerServer:
    def __init__(self, bot):
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

    def build_app(self) -> web.Application:
        from helpers.custom_roles import images
        from web.custom_role_picker import CustomRolePicker, MULTIPART_OVERHEAD
        app = web.Application(client_max_size=images.source_max_bytes() + MULTIPART_OVERHEAD)
        CustomRolePicker(self.bot).register(app)
        return app

    async def start(self) -> None:
        if not config.CUSTOM_ROLES_PICKER_ENABLED or self.runner:
            return
        self.runner = web.AppRunner(self.build_app(), access_log=custom_role_picker_logger)
        await self.runner.setup()
        configured_host = getattr(config, "DASHBOARD_PICKER_HOST", "127.0.0.1")
        host = _loopback_bind_host(configured_host)
        if host is None:
            custom_role_picker_logger.error("Custom-role picker refused to bind to non-loopback host %r.", configured_host)
            await self.runner.cleanup()
            self.runner = None
            return
        port = getattr(config, "DASHBOARD_PICKER_PORT", 8092)
        self.site = web.TCPSite(self.runner, host, port)
        try:
            await self.site.start()
        except Exception:
            await self.runner.cleanup()
            self.runner = None
            self.site = None
            raise
        self.bot.custom_role_picker_ready = True
        custom_role_picker_logger.info("Custom-role picker running privately on %s:%s behind the Rust dashboard proxy", host, port)

    async def stop(self) -> None:
        self.bot.custom_role_picker_ready = False
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
            self.site = None


# ------------------------------------------------------
