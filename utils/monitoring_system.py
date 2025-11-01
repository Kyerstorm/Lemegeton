"""
Comprehensive Monitoring System for Public Discord Bot Deployment
This module provides monitoring, metrics, and health checks for multi-guild bot deployment.
"""

import asyncio
import logging
import time
import json
import aiosqlite
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import psutil
import aiohttp
from dataclasses import dataclass, asdict
from pathlib import Path
import discord
from discord.ext import commands, tasks
import config

# Configure monitoring logger
monitor_logger = logging.getLogger("BotMonitor")
monitor_handler = logging.FileHandler("logs/monitoring.log")
monitor_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
))
monitor_logger.addHandler(monitor_handler)
monitor_logger.setLevel(logging.INFO)

@dataclass
class GuildMetrics:
    guild_id: int
    guild_name: str
    member_count: int
    registered_users: int
    active_users_24h: int
    commands_used_24h: int
    errors_24h: int
    last_activity: datetime
    
@dataclass
class SystemMetrics:
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    database_size_mb: float
    uptime_hours: float
    latency_ms: float

@dataclass
class BotMetrics:
    guild_count: int
    total_users: int
    total_registered_users: int
    commands_per_hour: int
    errors_per_hour: int
    top_commands: Dict[str, int]
    response_times: List[float]

class MonitoringSystem:
    def __init__(self, bot: commands.Bot, database_path: Optional[str] = None):
        """Monitoring system.

        database_path: path to the sqlite DB. If None, falls back to config.DB_PATH.
    """
        self.bot = bot
        # Use configured DB path by default to avoid accidental creation of database.db in repo root
        self.database_path = str(database_path or getattr(config, 'DB_PATH', 'data/database.db'))
        self.start_time = datetime.utcnow()
        self.command_usage = {}
        self.error_count = 0
        self.response_times = []
        self.guild_activity = {}

        # Metrics storage
        self.metrics_file = "monitoring_metrics.json"
        self.load_historical_metrics()
        
    def load_historical_metrics(self):
        """Load historical metrics from file"""
        try:
            if Path(self.metrics_file).exists():
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    self.command_usage = data.get('command_usage', {})
                    self.error_count = data.get('error_count', 0)
                    monitor_logger.info("📊 Loaded historical metrics")
        except Exception as e:
            monitor_logger.error(f"Failed to load historical metrics: {e}")
            
    def save_metrics(self):
        """Save metrics to file"""
        try:
            data = {
                'command_usage': self.command_usage,
                'error_count': self.error_count,
                'last_updated': datetime.utcnow().isoformat()
            }
            with open(self.metrics_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            monitor_logger.error(f"Failed to save metrics: {e}")

    async def get_guild_metrics(self, guild_id: int) -> Optional[GuildMetrics]:
        """Get metrics for a specific guild"""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return None
                
            # Database queries for guild-specific metrics
            conn = aiosqlite.connect(self.database_path)
            cursor = conn.cursor()
            
            # Registered users in this guild
            cursor.execute("SELECT COUNT(*) FROM users WHERE guild_id = ?", (guild_id,))
            registered_users = cursor.fetchone()[0]
            
            # Active users in last 24h (from command logs or activity)
            yesterday = datetime.utcnow() - timedelta(days=1)
            
            # Commands used in last 24h for this guild (would need command logging)
            commands_24h = self.guild_activity.get(guild_id, {}).get('commands_24h', 0)
            
            # Errors in last 24h for this guild
            errors_24h = self.guild_activity.get(guild_id, {}).get('errors_24h', 0)
            
            # Last activity timestamp
            last_activity = self.guild_activity.get(guild_id, {}).get('last_activity', datetime.utcnow())
            
            conn.close()
            
            return GuildMetrics(
                guild_id=guild_id,
                guild_name=guild.name,
                member_count=guild.member_count,
                registered_users=registered_users,
                active_users_24h=0,  # Would need activity tracking
                commands_used_24h=commands_24h,
                errors_24h=errors_24h,
                last_activity=last_activity
            )
            
        except Exception as e:
            monitor_logger.error(f"Failed to get guild metrics for {guild_id}: {e}")
            return None

    async def get_system_metrics(self) -> SystemMetrics:
        """Get system performance metrics"""
        try:
            # CPU and Memory
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('.')
            
            # Database size
            db_size = Path(self.database_path).stat().st_size / (1024 * 1024)  # MB
            
            # Bot uptime
            uptime = (datetime.utcnow() - self.start_time).total_seconds() / 3600
            
            # Bot latency
            latency = self.bot.latency * 1000  # Convert to ms
            
            return SystemMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                disk_percent=disk.percent,
                database_size_mb=round(db_size, 2),
                uptime_hours=round(uptime, 2),
                latency_ms=round(latency, 2)
            )
            
        except Exception as e:
            monitor_logger.error(f"Failed to get system metrics: {e}")
            return SystemMetrics(0, 0, 0, 0, 0, 0)

    async def get_bot_metrics(self) -> BotMetrics:
        """Get bot-wide metrics (defensive against missing DB/tables)"""
        try:
            # Guild count
            guild_count = len(self.bot.guilds)

            # Total users across all guilds
            total_users = sum(guild.member_count for guild in self.bot.guilds)

            # Registered users from database - handle DB/table missing gracefully
            total_registered = 0
            try:
                conn = aiosqlite.connect(self.database_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(DISTINCT discord_id) FROM users")
                row = cursor.fetchone()
                total_registered = (row[0] if row and row[0] is not None else 0)
                conn.close()
            except sqlite3.Error as db_err:
                # Log a warning once per monitoring loop iteration but don't raise
                monitor_logger.warning(f"Monitoring DB unavailable or missing tables, continuing with zeroed registered users: {db_err}")

            # Commands per hour (last hour)
            commands_per_hour = sum(self.command_usage.values())

            # Top commands
            top_commands = dict(sorted(self.command_usage.items(), key=lambda x: x[1], reverse=True)[:10])

            return BotMetrics(
                guild_count=guild_count,
                total_users=total_users,
                total_registered_users=total_registered,
                commands_per_hour=commands_per_hour,
                errors_per_hour=self.error_count,
                top_commands=top_commands,
                response_times=self.response_times[-100:]  # Last 100 response times
            )

        except Exception as e:
            monitor_logger.error(f"Failed to get bot metrics: {e}")
            return BotMetrics(0, 0, 0, 0, 0, {}, [])

    def record_command_usage(self, command_name: str, guild_id: int, response_time: float):
        """Record command usage for monitoring"""
        self.command_usage[command_name] = self.command_usage.get(command_name, 0) + 1
        self.response_times.append(response_time)
        
        # Update guild activity
        if guild_id not in self.guild_activity:
            self.guild_activity[guild_id] = {'commands_24h': 0, 'errors_24h': 0}
        
        self.guild_activity[guild_id]['commands_24h'] += 1
        self.guild_activity[guild_id]['last_activity'] = datetime.utcnow()
        
        monitor_logger.info(f"📊 Command '{command_name}' used in guild {guild_id} - Response time: {response_time:.3f}s")

    def record_error(self, error: Exception, guild_id: Optional[int] = None, command_name: Optional[str] = None):
        """Record error for monitoring"""
        self.error_count += 1
        
        if guild_id and guild_id in self.guild_activity:
            self.guild_activity[guild_id]['errors_24h'] += 1
            
        monitor_logger.error(f"🚨 Error recorded: {type(error).__name__}: {error} | Guild: {guild_id} | Command: {command_name}")

    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        try:
            health = {
                'status': 'healthy',
                'timestamp': datetime.utcnow().isoformat(),
                'checks': {}
            }
            
            # Bot connection check
            health['checks']['bot_ready'] = self.bot.is_ready()
            
            # Database connection check
            try:
                conn = aiosqlite.connect(self.database_path)
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                conn.close()
                health['checks']['database'] = True
            except:
                health['checks']['database'] = False
                health['status'] = 'degraded'
            
            # Memory usage check
            memory = psutil.virtual_memory()
            health['checks']['memory_ok'] = memory.percent < 90
            if memory.percent >= 90:
                health['status'] = 'degraded'
            
            # Disk space check
            disk = psutil.disk_usage('.')
            health['checks']['disk_ok'] = disk.percent < 90
            if disk.percent >= 90:
                health['status'] = 'degraded'
                
            # Latency check
            health['checks']['latency_ok'] = self.bot.latency < 1.0  # Less than 1 second
            if self.bot.latency >= 1.0:
                health['status'] = 'degraded'
            
            # Recent errors check
            health['checks']['low_errors'] = self.error_count < 100  # Less than 100 errors
            if self.error_count >= 100:
                health['status'] = 'degraded'
                
            return health
            
        except Exception as e:
            monitor_logger.error(f"Health check failed: {e}")
            return {
                'status': 'unhealthy',
                'timestamp': datetime.utcnow().isoformat(),
                'error': str(e)
            }

    @tasks.loop(minutes=5)
    async def monitoring_task(self):
        """Periodic monitoring task"""
        try:
            # Get current metrics
            system_metrics = await self.get_system_metrics()
            bot_metrics = await self.get_bot_metrics()
            
            # Log key metrics
            monitor_logger.info(f"🖥️  System: CPU {system_metrics.cpu_percent}%, RAM {system_metrics.memory_percent}%, Latency {system_metrics.latency_ms}ms")
            monitor_logger.info(f"🤖 Bot: {bot_metrics.guild_count} guilds, {bot_metrics.total_registered_users} registered users, {len(bot_metrics.response_times)} recent commands")
            
            # Check for alerts
            await self.check_alerts(system_metrics, bot_metrics)
            
            # Save metrics
            self.save_metrics()
            
            # Reset hourly counters if needed
            current_hour = datetime.utcnow().hour
            if not hasattr(self, 'last_reset_hour') or self.last_reset_hour != current_hour:
                self.reset_hourly_counters()
                self.last_reset_hour = current_hour
                
        except Exception as e:
            monitor_logger.error(f"Monitoring task failed: {e}")

    async def check_alerts(self, system_metrics: SystemMetrics, bot_metrics: BotMetrics):
        """Check for alert conditions"""
        alerts = []
        
        # High CPU usage
        if system_metrics.cpu_percent > 80:
            alerts.append(f"🚨 High CPU usage: {system_metrics.cpu_percent}%")
            
        # High memory usage
        if system_metrics.memory_percent > 85:
            alerts.append(f"🚨 High memory usage: {system_metrics.memory_percent}%")
            
        # High latency
        if system_metrics.latency_ms > 1000:
            alerts.append(f"🚨 High latency: {system_metrics.latency_ms}ms")
            
        # Many errors
        if self.error_count > 50:
            alerts.append(f"🚨 High error rate: {self.error_count} errors")
            
        # Database size growing large
        if system_metrics.database_size_mb > 1000:  # 1GB
            alerts.append(f"⚠️ Large database: {system_metrics.database_size_mb}MB")
            
        # Log alerts
        for alert in alerts:
            monitor_logger.warning(alert)
            
        return alerts

    def reset_hourly_counters(self):
        """Reset counters that track hourly metrics"""
        self.command_usage = {}
        self.error_count = 0
        self.response_times = []
        
        # Reset guild 24h counters daily
        current_day = datetime.utcnow().day
        if not hasattr(self, 'last_daily_reset') or self.last_daily_reset != current_day:
            for guild_data in self.guild_activity.values():
                guild_data['commands_24h'] = 0
                guild_data['errors_24h'] = 0
            self.last_daily_reset = current_day
        
        monitor_logger.info("🔄 Reset hourly monitoring counters")

    async def generate_report(self) -> str:
        """Generate a comprehensive monitoring report"""
        try:
            system_metrics = await self.get_system_metrics()
            bot_metrics = await self.get_bot_metrics()
            health = await self.health_check()
            
            report = f"""
🤖 **Bot Monitoring Report**
Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC

**🏥 Health Status: {health['status'].upper()}**

**📊 System Metrics:**
• CPU Usage: {system_metrics.cpu_percent}%
• Memory Usage: {system_metrics.memory_percent}%
• Disk Usage: {system_metrics.disk_percent}%
• Database Size: {system_metrics.database_size_mb} MB
• Uptime: {system_metrics.uptime_hours} hours
• Latency: {system_metrics.latency_ms}ms

**🤖 Bot Metrics:**
• Guilds: {bot_metrics.guild_count}
• Total Users: {bot_metrics.total_users:,}
• Registered Users: {bot_metrics.total_registered_users}
• Commands/hour: {bot_metrics.commands_per_hour}
• Errors/hour: {bot_metrics.errors_per_hour}

**🔥 Top Commands:**
"""
            
            for cmd, count in list(bot_metrics.top_commands.items())[:5]:
                report += f"• {cmd}: {count} uses\n"
                
            # Average response time
            if bot_metrics.response_times:
                avg_response = sum(bot_metrics.response_times) / len(bot_metrics.response_times)
                report += f"\n**⚡ Avg Response Time:** {avg_response:.3f}s"
                
            return report
            
        except Exception as e:
            monitor_logger.error(f"Failed to generate report: {e}")
            return f"❌ Failed to generate report: {e}"

# Global monitoring instance
monitoring_system: Optional[MonitoringSystem] = None

def setup_monitoring(bot: commands.Bot) -> MonitoringSystem:
    """Initialize monitoring system"""
    global monitoring_system
    # Pass configured DB path so monitoring reads the same DB used by the rest of the app
    monitoring_system = MonitoringSystem(bot, database_path=getattr(config, 'DB_PATH', None))
    # Do NOT start the @tasks.loop here because the bot's event loop may not be
    # running yet (setup_monitoring can be called during module import or before
    # bot.run()). Starting the loop must happen when the event loop is active.
    monitor_logger.info("🚀 Monitoring system initialized (task start deferred)")
    return monitoring_system

def get_monitoring() -> Optional[MonitoringSystem]:
    """Get the global monitoring instance"""
    return monitoring_system

class MonitoringCommands(commands.Cog):
    """Commands for monitoring and health checks"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.monitoring = get_monitoring()
        
    @commands.command(name='health')
    @commands.has_permissions(administrator=True)
    async def health_check_command(self, ctx):
        """Check bot health status"""
        if not self.monitoring:
            await ctx.send("❌ Monitoring system not initialized")
            return
            
        health = await self.monitoring.health_check()
        
        embed = discord.Embed(
            title=f"🏥 Bot Health: {health['status'].upper()}",
            color=discord.Color.green() if health['status'] == 'healthy' else discord.Color.yellow()
        )
        
        checks = health.get('checks', {})
        for check, status in checks.items():
            embed.add_field(
                name=check.replace('_', ' ').title(),
                value="✅ Pass" if status else "❌ Fail",
                inline=True
            )
            
        embed.timestamp = datetime.utcnow()
        await ctx.send(embed=embed)
        
    @commands.command(name='metrics')
    @commands.has_permissions(administrator=True)
    async def metrics_command(self, ctx):
        """Show bot metrics"""
        if not self.monitoring:
            await ctx.send("❌ Monitoring system not initialized")
            return
            
        report = await self.monitoring.generate_report()
        
        # Split long report if needed
        if len(report) > 2000:
            chunks = [report[i:i+2000] for i in range(0, len(report), 2000)]
            for chunk in chunks:
                await ctx.send(f"```{chunk}```")
        else:
            await ctx.send(f"```{report}```")
            
    @commands.command(name='guild-metrics')
    @commands.has_permissions(administrator=True)
    async def guild_metrics_command(self, ctx, guild_id: int = None):
        """Show metrics for specific guild"""
        if not self.monitoring:
            await ctx.send("❌ Monitoring system not initialized")
            return
            
        target_guild_id = guild_id or ctx.guild.id
        metrics = await self.monitoring.get_guild_metrics(target_guild_id)
        
        if not metrics:
            await ctx.send(f"❌ Could not get metrics for guild {target_guild_id}")
            return
            
        embed = discord.Embed(
            title=f"📊 Guild Metrics: {metrics.guild_name}",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Members", value=metrics.member_count, inline=True)
        embed.add_field(name="Registered Users", value=metrics.registered_users, inline=True)
        embed.add_field(name="Commands (24h)", value=metrics.commands_used_24h, inline=True)
        embed.add_field(name="Errors (24h)", value=metrics.errors_24h, inline=True)
        embed.add_field(name="Last Activity", value=metrics.last_activity.strftime('%Y-%m-%d %H:%M:%S'), inline=True)
        
        embed.timestamp = datetime.utcnow()
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    """Setup monitoring cog"""
    await bot.add_cog(MonitoringCommands(bot))