"""Run the existing custom-role picker on a private loopback port.

The Rust dashboard reverse-proxies /custom-roles to this service. The picker
continues to perform its existing Discord/member/role validation in Python.
"""
from __future__ import annotations

import logging

from aiohttp import web

import config
from web.custom_role_picker import CustomRolePicker

logger = logging.getLogger("web.custom_role_picker_server")


class CustomRolePickerServer:
    def __init__(self, bot):
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

    def build_app(self) -> web.Application:
        app = web.Application()
        CustomRolePicker(self.bot).register(app)
        return app

    async def start(self) -> None:
        if not config.CUSTOM_ROLES_PICKER_ENABLED or self.runner:
            return
        self.runner = web.AppRunner(self.build_app(), access_log=logger)
        await self.runner.setup()
        host = getattr(config, "DASHBOARD_PICKER_HOST", "127.0.0.1")
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
        logger.info("Custom-role picker running privately on %s:%s behind the Rust dashboard proxy", host, port)

    async def stop(self) -> None:
        self.bot.custom_role_picker_ready = False
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
            self.site = None
