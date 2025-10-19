#!/usr/bin/env python3
"""
Gradual Deployment Script for Discord Bot
Implements the gradual rollout strategy from DEPLOYMENT_CHECKLIST.md
"""

import asyncio
import json
import sqlite3
import logging
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import time
import config

# Setup deployment logging
deploy_logger = logging.getLogger("Deployment")
deploy_handler = logging.FileHandler("logs/deployment.log")
deploy_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)s | DEPLOY | %(message)s"
))
deploy_logger.addHandler(deploy_handler)
deploy_logger.setLevel(logging.INFO)

class DeploymentManager:
    def __init__(self, database_path: str = None):
        # Use provided path, otherwise fall back to configured DB_PATH
        self.database_path = str(database_path or getattr(config, 'DB_PATH', os.path.join(os.path.dirname(__file__), '..', 'data', 'database.db')))
        self.deployment_config = {
            "phase": "pre-deployment",
            "start_time": None,
            "test_guilds": [],
            "beta_guilds": [],
            "metrics": {},
            "issues": []
        }
        self.load_deployment_state()
    
    def load_deployment_state(self):
        """Load deployment state from file"""
        try:
            if Path("deployment_state.json").exists():
                with open("deployment_state.json", "r") as f:
                    self.deployment_config.update(json.load(f))
                deploy_logger.info(f"📊 Loaded deployment state: Phase {self.deployment_config['phase']}")
        except Exception as e:
            deploy_logger.error(f"Failed to load deployment state: {e}")
    
    def save_deployment_state(self):
        """Save deployment state to file"""
        try:
            self.deployment_config["last_updated"] = datetime.utcnow().isoformat()
            with open("deployment_state.json", "w") as f:
                json.dump(self.deployment_config, f, indent=2)
            deploy_logger.info("💾 Saved deployment state")
        except Exception as e:
            deploy_logger.error(f"Failed to save deployment state: {e}")
    
    def check_pre_deployment_requirements(self):
        """Check all pre-deployment requirements"""
        deploy_logger.info("🔍 Checking pre-deployment requirements...")
        
        checks = {
            "database_exists": False,
            "backup_created": False,
            "multi_guild_ready": False,
            "monitoring_available": False,
            "logs_directory": False
        }
        
        # Database exists and accessible
        try:
            if Path(self.database_path).exists():
                conn = sqlite3.connect(self.database_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users")
                user_count = cursor.fetchone()[0]
                conn.close()
                checks["database_exists"] = True
                deploy_logger.info(f"✅ Database accessible with {user_count} users")
            else:
                deploy_logger.error("❌ Database file not found")
        except Exception as e:
            deploy_logger.error(f"❌ Database check failed: {e}")
        
        # Backup exists
        backup_files = list(Path(".").glob("database_backup_*.db"))
        if backup_files:
            latest_backup = max(backup_files, key=lambda p: p.stat().st_mtime)
            checks["backup_created"] = True
            deploy_logger.info(f"✅ Latest backup: {latest_backup}")
        else:
            deploy_logger.error("❌ No database backup found")
        
        # Multi-guild readiness
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Check if users table has guild_id
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            if "guild_id" in columns:
                checks["multi_guild_ready"] = True
                deploy_logger.info("✅ Multi-guild support confirmed")
            else:
                deploy_logger.error("❌ Users table missing guild_id column")
            
            conn.close()
        except Exception as e:
            deploy_logger.error(f"❌ Multi-guild check failed: {e}")
        
        # Logs directory
        if Path("logs").exists():
            checks["logs_directory"] = True
            deploy_logger.info("✅ Logs directory exists")
        else:
            deploy_logger.error("❌ Logs directory missing")
        
        # Summary
        passed = sum(1 for check in checks.values() if check)
        total = len(checks)
        deploy_logger.info(f"📊 Pre-deployment checks: {passed}/{total} passed")
        
        if passed == total:
            deploy_logger.info("🎉 All pre-deployment requirements met!")
            return True
        else:
            deploy_logger.error("❌ Pre-deployment requirements not met")
            return False
    
    def create_deployment_backup(self):
        """Create a deployment backup"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"deployment_backup_{timestamp}.db"
            
            # Copy database
            import shutil
            shutil.copy2(self.database_path, backup_name)
            
            deploy_logger.info(f"💾 Created deployment backup: {backup_name}")
            return backup_name
        except Exception as e:
            deploy_logger.error(f"❌ Failed to create deployment backup: {e}")
            return None
    
    def start_phase_1_testing(self):
        """Start Phase 1: Limited Beta Testing"""
        deploy_logger.info("🚀 Starting Phase 1: Limited Beta Testing")
        
        self.deployment_config["phase"] = "phase-1-testing"
        self.deployment_config["start_time"] = datetime.utcnow().isoformat()
        
        # Instructions for manual testing
        instructions = """
        
🧪 PHASE 1: LIMITED BETA TESTING (1-2 test servers)

MANUAL STEPS REQUIRED:
1. Add your bot to 1-2 test Discord servers
2. Verify bot has required permissions:
   - Send Messages
   - Use Slash Commands
   - Embed Links
   - Read Message History
   - Add Reactions

3. Test core functionality in each server:
   - /profile command (should show registration prompt)
   - Register with AniList account
   - /profile command again (should show profile)
   - Verify users in different servers are isolated

4. Monitor for 24-48 hours:
   - Check logs/deployment.log for errors
   - Run: python deployment_manager.py --check-health
   - Verify no data mixing between servers

5. When ready for Phase 2:
   - Run: python deployment_manager.py --advance-phase

        """
        
        print(instructions)
        deploy_logger.info("📋 Phase 1 testing instructions provided")
        
        self.save_deployment_state()
    
    def check_phase_1_health(self):
        """Check health during Phase 1"""
        deploy_logger.info("🏥 Checking Phase 1 health...")
        
        issues = []
        metrics = {}
        
        try:
            # Check database health
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Count guilds with users
            cursor.execute("SELECT COUNT(DISTINCT guild_id) FROM users WHERE guild_id IS NOT NULL")
            guild_count = cursor.fetchone()[0]
            metrics["active_guilds"] = guild_count
            
            if guild_count < 1:
                issues.append("No guilds with registered users found")
            
            # Check for recent activity (users created in last 48 hours)
            two_days_ago = datetime.now() - timedelta(days=2)
            cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (two_days_ago.isoformat(),))
            recent_users = cursor.fetchone()[0]
            metrics["recent_registrations"] = recent_users
            
            if recent_users < 1:
                issues.append("No recent user registrations in test phase")
            
            # Check for data isolation (users should have different guild_ids)
            cursor.execute("SELECT guild_id, COUNT(*) FROM users GROUP BY guild_id")
            guild_distribution = cursor.fetchall()
            metrics["guild_distribution"] = dict(guild_distribution)
            
            if len(guild_distribution) < 2:
                issues.append("Multi-guild testing not detected (need at least 2 guilds)")
            
            conn.close()
            
            # Check log files for errors
            if Path("logs/bot.log").exists():
                with open("logs/bot.log", "r") as f:
                    recent_logs = f.readlines()[-100:]  # Last 100 lines
                    error_count = sum(1 for line in recent_logs if "ERROR" in line or "CRITICAL" in line)
                    metrics["recent_errors"] = error_count
                    
                    if error_count > 10:
                        issues.append(f"High error count in logs: {error_count} errors")
            
            # Update deployment config
            self.deployment_config["metrics"] = metrics
            self.deployment_config["issues"] = issues
            self.save_deployment_state()
            
            # Report results
            deploy_logger.info(f"📊 Phase 1 Metrics: {metrics}")
            
            if issues:
                deploy_logger.warning(f"⚠️ Issues found: {issues}")
                print("\n⚠️ PHASE 1 HEALTH CHECK - ISSUES FOUND:")
                for issue in issues:
                    print(f"  • {issue}")
            else:
                deploy_logger.info("✅ Phase 1 health check passed!")
                print("\n✅ PHASE 1 HEALTH CHECK PASSED!")
                print("Bot is ready for Phase 2 when you are ready.")
            
            return len(issues) == 0
            
        except Exception as e:
            deploy_logger.error(f"❌ Phase 1 health check failed: {e}")
            return False
    
    def advance_to_phase_2(self):
        """Advance to Phase 2: Expanded Beta"""
        deploy_logger.info("📈 Advancing to Phase 2: Expanded Beta")
        
        self.deployment_config["phase"] = "phase-2-beta"
        self.deployment_config["phase_2_start"] = datetime.utcnow().isoformat()
        
        instructions = """
        
🚀 PHASE 2: EXPANDED BETA (5-10 servers)

MANUAL STEPS REQUIRED:
1. Invite bot to 3-8 additional servers (total 5-10 servers)
2. Share bot invite link with trusted communities
3. Monitor performance metrics:
   - Check resource usage (CPU, memory)
   - Monitor command response times

4. Gather user feedback:
   - Test all major commands across different servers
   - Verify guild isolation is working
   - Check for any user-reported issues

5. Monitor for 1 week:
   - Daily health checks: python deployment_manager.py --check-health
   - Weekly metrics review
   - Address any performance issues

6. When ready for public launch:
   - Run: python deployment_manager.py --launch-public

        """
        
        print(instructions)
        deploy_logger.info("📋 Phase 2 beta instructions provided")
        
        self.save_deployment_state()
    
    def launch_public(self):
        """Launch publicly"""
        deploy_logger.info("🌟 Launching publicly!")
        
        self.deployment_config["phase"] = "public"
        self.deployment_config["public_launch"] = datetime.utcnow().isoformat()
        
        instructions = """
        
🎉 PUBLIC LAUNCH!

YOUR BOT IS NOW READY FOR PUBLIC USE!

NEXT STEPS:
1. Share your bot invite link publicly
2. Set up continuous monitoring:
   - Monitor health: python deployment_manager.py --check-health
   - Check logs regularly

3. Post-launch monitoring:
   - Week 1: Check metrics every 4 hours
   - Week 2-4: Daily health checks
   - Month 1+: Weekly reviews

4. Optional enhancements (post-launch):
   - Update challenge cogs for full guild isolation
   - Add advanced features based on user feedback
   - Optimize performance based on usage patterns

🎊 CONGRATULATIONS ON YOUR SUCCESSFUL DEPLOYMENT!

        """
        
        print(instructions)
        deploy_logger.info("🎉 Public launch completed!")
        
        self.save_deployment_state()

def main():
    if len(sys.argv) < 2:
        print("Usage: python deployment_manager.py [--check-requirements|--start-testing|--check-health|--advance-phase|--launch-public]")
        return
    
    manager = DeploymentManager()
    command = sys.argv[1]
    
    if command == "--check-requirements":
        if manager.check_pre_deployment_requirements():
            print("✅ All requirements met! Ready to start testing.")
        else:
            print("❌ Requirements not met. Check logs/deployment.log for details.")
    
    elif command == "--start-testing":
        if manager.check_pre_deployment_requirements():
            backup = manager.create_deployment_backup()
            if backup:
                manager.start_phase_1_testing()
        else:
            print("❌ Pre-deployment requirements not met")
    
    elif command == "--check-health":
        if manager.deployment_config["phase"] == "phase-1-testing":
            manager.check_phase_1_health()
        else:
            print(f"Current phase: {manager.deployment_config['phase']}")
            # Could add health checks for other phases
    
    elif command == "--advance-phase":
        if manager.deployment_config["phase"] == "phase-1-testing":
            if manager.check_phase_1_health():
                manager.advance_to_phase_2()
            else:
                print("❌ Phase 1 health check failed. Address issues before advancing.")
        else:
            print(f"Cannot advance from phase: {manager.deployment_config['phase']}")
    
    elif command == "--launch-public":
        if manager.deployment_config["phase"] == "phase-2-beta":
            manager.launch_public()
        else:
            print(f"Cannot launch public from phase: {manager.deployment_config['phase']}")
    
    else:
        print("Unknown command. Use --help for options.")

if __name__ == "__main__":
    main()