import discord
from discord.ext import commands
from discord import app_commands, ui
import requests
import random
import string
import json
import os
import aiohttp
from datetime import datetime, timedelta

# Bot configuration
TOKEN = 'TOKEN'  # Replace with your Discord bot token
SELLER_KEY = 'd50f68884fcd5020a56bf88351ef5082'  # Seller key from KeyAuth
AUTH_BASE_URL = 'https://keyauth.win/api/seller/'
PREFIX = '?'

# Colors for embeds
COLORS = {
    'success': discord.Color.green(),
    'error': discord.Color.red(),
    'info': discord.Color.blue(),
    'warning': discord.Color.gold()
}

# Authorized user IDs - replace with actual authorized Discord user IDs
AUTHORIZED_USERS = [
    '1362133591156330597',
    '854747808907919431',
    '1359408204710416455'
]

# HWID Reset Cooldown Tracking
hwid_resets = {}  # Format: {user_id: last_reset_time}
HWID_COOLDOWN_DAYS = 3
CUSTOMER_ROLE_ID = 1359407688144130121

# Configure intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Helper functions
def is_authorized(ctx):
    """Check if the user is authorized to use this command"""
    return str(ctx.author.id) in AUTHORIZED_USERS

def log_command(ctx, action, details=None):
    """Log command usage to a file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {ctx.author} ({ctx.author.id}) used {action}"
    if details:
        log_message += f" - {details}"

    print(log_message)
    with open("keyauth_logs.txt", "a") as log_file:
        log_file.write(log_message + "\n")

def make_keyauth_request(params):
    """Make a request to KeyAuth API"""
    params['sellerkey'] = SELLER_KEY
    response = requests.get(AUTH_BASE_URL, params=params)
    return response.text

def generate_mask():
    """Generate a license key mask using the specified format"""
    mask = "PULSE-PRIVATE-"
    for _ in range(6):
        mask += random.choice(string.ascii_uppercase + string.digits)
    mask += "-"
    for _ in range(6):
        mask += random.choice(string.ascii_uppercase + string.digits)
    return mask

def check_hwid_cooldown(user_id):
    """Check if a user is on cooldown for HWID reset"""
    if user_id not in hwid_resets:
        return False

    last_reset = hwid_resets[user_id]
    cooldown_end = last_reset + timedelta(days=HWID_COOLDOWN_DAYS)
    now = datetime.now()

    if now < cooldown_end:
        return True
    return False

def get_cooldown_remaining(user_id):
    """Get the remaining cooldown time for a user's HWID reset"""
    if user_id not in hwid_resets:
        return None

    last_reset = hwid_resets[user_id]
    cooldown_end = last_reset + timedelta(days=HWID_COOLDOWN_DAYS)
    now = datetime.now()

    if now < cooldown_end:
        remaining = cooldown_end - now
        return remaining
    return None

# UI Components
class HWIDResetModal(ui.Modal, title="Reset HWID"):
    license_key = ui.TextInput(label="License Key", placeholder="Enter your license key", required=True)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        key = self.license_key.value
        user_id = str(interaction.user.id)

        # Check if user has the customer role
        has_customer_role = False
        for role in interaction.user.roles:
            if role.id == CUSTOMER_ROLE_ID:
                has_customer_role = True
                break

        if not has_customer_role:
            await interaction.response.send_message("❌ You need the Customer role to reset your HWID.", ephemeral=True)
            return

        # Check cooldown
        if check_hwid_cooldown(user_id):
            remaining = get_cooldown_remaining(user_id)
            days = remaining.days
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60

            await interaction.response.send_message(
                f"⏳ You're on cooldown! You can reset your HWID again in {days} days, {hours} hours, and {minutes} minutes.", 
                ephemeral=True
            )
            return

        # Perform HWID reset
        try:
            params = {
                'type': 'resetuser',
                'user': key
            }

            response = make_keyauth_request(params)

            if "success" in response.lower():
                # Record the reset time
                hwid_resets[user_id] = datetime.now()

                # Save HWID reset data to file
                try:
                    with open("hwid_resets.json", "w") as f:
                        json_data = {k: v.strftime("%Y-%m-%d %H:%M:%S") for k, v in hwid_resets.items()}
                        json.dump(json_data, f)
                except Exception as e:
                    print(f"Error saving HWID reset data: {e}")

                embed = discord.Embed(
                    title="HWID Reset Successful",
                    description=f"✅ Your HWID has been reset for key: `{key}`",
                    color=COLORS['success']
                )
                embed.set_footer(text=f"You can reset your HWID again in {HWID_COOLDOWN_DAYS} days.")

                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Failed to reset HWID: {response}", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Error resetting HWID: {str(e)}", ephemeral=True)

class KeyAuthView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Reset HWID", style=discord.ButtonStyle.primary, custom_id="hwid_reset_button")
    async def hwid_reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = HWIDResetModal(self.bot)
        await interaction.response.send_modal(modal)

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    print(f'Serving {len(bot.guilds)} servers')

    # Load HWID reset data
    try:
        if os.path.exists("hwid_resets.json"):
            with open("hwid_resets.json", "r") as f:
                data = json.load(f)
                hwid_resets.update({k: datetime.strptime(v, "%Y-%m-%d %H:%M:%S") for k, v in data.items()})
            print("HWID reset data loaded successfully")
    except Exception as e:
        print(f"Error loading HWID reset data: {e}")

    # Set up persistent buttons
    try:
        bot.add_view(KeyAuthView(bot))
        print("Added persistent views")
    except Exception as e:
        print(f"Error setting up persistent views: {e}")

    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help for commands"))

@bot.command(name="ping", help="Check if the bot is responsive")
async def ping(ctx):
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot latency: `{round(bot.latency * 1000)}ms`",
        color=COLORS['info']
    )
    await ctx.send(embed=embed)

@bot.command(name="genkey", help="Generate a license key")
async def genkey(ctx, days: int = 1, level: int = 1, amount: int = 1):
    if not is_authorized(ctx):
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ You are not authorized to use this command.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    if amount > 50:
        embed = discord.Embed(
            title="Limit Exceeded",
            description="⚠️ You can only generate up to 50 keys at once.",
            color=COLORS['warning']
        )
        await ctx.send(embed=embed)
        return

    if days <= 0 or level <= 0 or amount <= 0:
        embed = discord.Embed(
            title="Invalid Parameters",
            description="⚠️ Days, level, and amount must be positive numbers.",
            color=COLORS['warning']
        )
        await ctx.send(embed=embed)
        return

    try:
        mask = generate_mask()
        params = {
            'type': 'add',
            'expiry': days,
            'mask': mask,
            'level': level,
            'amount': amount,
            'format': 'text'
        }

        response = make_keyauth_request(params)
        log_command(ctx, "genkey", f"Generated {amount} keys for {days} days at level {level}")

        # Send the keys to the user in a DM
        if amount == 1:
            embed = discord.Embed(
                title="Key Generated",
                description=f"✅ Generated 1 license key for {days} day(s) at level {level}.",
                color=COLORS['success']
            )
            await ctx.send(embed=embed)

            dm_embed = discord.Embed(
                title="Your License Key",
                description=f"```{response}```",
                color=COLORS['success']
            )
            await ctx.author.send(embed=dm_embed)
        else:
            embed = discord.Embed(
                title="Keys Generated",
                description=f"✅ Generated {amount} license keys for {days} day(s) at level {level}.",
                color=COLORS['success']
            )
            await ctx.send(embed=embed)

            # Split keys into chunks to avoid message limits
            keys = response.strip().split("\n")
            chunks = [keys[i:i+10] for i in range(0, len(keys), 10)]

            for i, chunk in enumerate(chunks):
                dm_embed = discord.Embed(
                    title=f"Your License Keys (Part {i+1}/{len(chunks)})",
                    description=f"```{chr(10).join(chunk)}```",
                    color=COLORS['success']
                )
                await ctx.author.send(embed=dm_embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error generating keys: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        print(f"Error generating keys: {str(e)}")

@bot.command(name="verifykey", help="Verify a license key")
async def verifykey(ctx, key: str):
    try:
        params = {
            'type': 'verify',
            'key': key
        }

        response = make_keyauth_request(params)
        log_command(ctx, "verifykey", f"Key: {key}")

        if "failed" in response.lower():
            embed = discord.Embed(
                title="Key Verification",
                description=f"❌ License key invalid or expired: {response}",
                color=COLORS['error']
            )
        else:
            embed = discord.Embed(
                title="Key Verification",
                description=f"✅ License key is valid: {response}",
                color=COLORS['success']
            )

        await ctx.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error verifying key: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="deletekey", help="Delete a license key")
async def deletekey(ctx, key: str):
    if not is_authorized(ctx):
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ You are not authorized to use this command.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    try:
        params = {
            'type': 'del',
            'key': key
        }

        response = make_keyauth_request(params)
        log_command(ctx, "deletekey", f"Key: {key}")

        if "success" in response.lower():
            embed = discord.Embed(
                title="Key Deleted",
                description=f"✅ Successfully deleted key: `{key}`",
                color=COLORS['success']
            )
        else:
            embed = discord.Embed(
                title="Delete Failed",
                description=f"❌ Failed to delete key: {response}",
                color=COLORS['error']
            )

        await ctx.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error deleting key: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="resethwid", help="Reset HWID for a license key")
async def resethwid(ctx, key: str):
    if not is_authorized(ctx):
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ You are not authorized to use this command.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    try:
        params = {
            'type': 'resetuser',
            'user': key
        }

        response = make_keyauth_request(params)
        log_command(ctx, "resethwid", f"Key: {key}")

        if "success" in response.lower():
            embed = discord.Embed(
                title="HWID Reset",
                description=f"✅ Successfully reset HWID for key: `{key}`",
                color=COLORS['success']
            )
        else:
            embed = discord.Embed(
                title="Reset Failed",
                description=f"❌ Failed to reset HWID: {response}",
                color=COLORS['error']
            )

        await ctx.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error resetting HWID: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="keyinfo", help="Get information about a license key")
async def keyinfo(ctx, key: str):
    if not is_authorized(ctx):
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ You are not authorized to use this command.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    try:
        params = {
            'type': 'info',
            'key': key
        }

        response = make_keyauth_request(params)
        log_command(ctx, "keyinfo", f"Key: {key}")

        try:
            data = json.loads(response)
            embed = discord.Embed(
                title="License Key Information",
                color=COLORS['info']
            )
            embed.add_field(name="Key", value=f"`{key}`", inline=False)

            # Add all available information to the embed
            for field, value in data.items():
                if field != "key":
                    embed.add_field(name=field.capitalize(), value=value, inline=True)

            await ctx.send(embed=embed)
        except json.JSONDecodeError:
            embed = discord.Embed(
                title="Information Error",
                description=f"❌ Failed to get key info: {response}",
                color=COLORS['error']
            )
            await ctx.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error getting key info: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="bankey", help="Ban a license key")
async def bankey(ctx, key: str, *, reason: str = "No reason provided"):
    if not is_authorized(ctx):
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ You are not authorized to use this command.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    try:
        params = {
            'type': 'ban',
            'key': key,
            'reason': reason
        }

        response = make_keyauth_request(params)
        log_command(ctx, "bankey", f"Key: {key}, Reason: {reason}")

        if "success" in response.lower():
            embed = discord.Embed(
                title="Key Banned",
                description=f"✅ Successfully banned key: `{key}`",
                color=COLORS['success']
            )
            embed.add_field(name="Reason", value=reason)
        else:
            embed = discord.Embed(
                title="Ban Failed",
                description=f"❌ Failed to ban key: {response}",
                color=COLORS['error']
            )

        await ctx.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error banning key: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="unbankey", help="Unban a license key")
async def unbankey(ctx, key: str):
    if not is_authorized(ctx):
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ You are not authorized to use this command.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    try:
        params = {
            'type': 'unban',
            'key': key
        }

        response = make_keyauth_request(params)
        log_command(ctx, "unbankey", f"Key: {key}")

        if "success" in response.lower():
            embed = discord.Embed(
                title="Key Unbanned",
                description=f"✅ Successfully unbanned key: `{key}`",
                color=COLORS['success']
            )
        else:
            embed = discord.Embed(
                title="Unban Failed",
                description=f"❌ Failed to unban key: {response}",
                color=COLORS['error']
            )

        await ctx.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error unbanning key: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="adduser", help="Add an authorized user")
async def adduser(ctx, user_id: str):
    if not is_authorized(ctx):
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ You are not authorized to use this command.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    if user_id in AUTHORIZED_USERS:
        embed = discord.Embed(
            title="Already Authorized",
            description="⚠️ This user is already authorized.",
            color=COLORS['warning']
        )
        await ctx.send(embed=embed)
        return

    try:
        # Load current authorized users
        if os.path.exists("authorized_users.json"):
            with open("authorized_users.json", "r") as file:
                users = json.load(file)
        else:
            users = AUTHORIZED_USERS.copy()

        # Add new user
        users.append(user_id)

        # Save updated list
        with open("authorized_users.json", "w") as file:
            json.dump(users, file)

        # Update runtime list
        AUTHORIZED_USERS.append(user_id)

        log_command(ctx, "adduser", f"Added user ID: {user_id}")

        embed = discord.Embed(
            title="User Authorized",
            description=f"✅ User with ID `{user_id}` has been authorized.",
            color=COLORS['success']
        )
        await ctx.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error adding authorized user: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="removeuser", help="Remove an authorized user")
async def removeuser(ctx, user_id: str):
    # Only the first user in the AUTHORIZED_USERS list can remove users
    if str(ctx.author.id) != AUTHORIZED_USERS[0]:
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ Only the primary admin can remove authorized users.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    if user_id not in AUTHORIZED_USERS:
        embed = discord.Embed(
            title="Not Authorized",
            description="⚠️ This user is not authorized.",
            color=COLORS['warning']
        )
        await ctx.send(embed=embed)
        return

    try:
        # Load current authorized users
        if os.path.exists("authorized_users.json"):
            with open("authorized_users.json", "r") as file:
                users = json.load(file)
        else:
            users = AUTHORIZED_USERS.copy()

        # Remove user
        if user_id in users:
            users.remove(user_id)

        # Save updated list
        with open("authorized_users.json", "w") as file:
            json.dump(users, file)

        # Update runtime list
        AUTHORIZED_USERS.remove(user_id)

        log_command(ctx, "removeuser", f"Removed user ID: {user_id}")

        embed = discord.Embed(
            title="User Removed",
            description=f"✅ User with ID `{user_id}` has been unauthorized.",
            color=COLORS['success']
        )
        await ctx.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error removing authorized user: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="listusers", help="List all authorized users")
async def listusers(ctx):
    if not is_authorized(ctx):
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ You are not authorized to use this command.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    try:
        embed = discord.Embed(
            title="Authorized Users",
            description="Users who can use administrative commands",
            color=COLORS['info']
        )

        # Try to load users from file first
        users = AUTHORIZED_USERS.copy()
        if os.path.exists("authorized_users.json"):
            with open("authorized_users.json", "r") as file:
                users = json.load(file)

        for i, user_id in enumerate(users):
            try:
                user = await bot.fetch_user(int(user_id))
                embed.add_field(
                    name=f"User {i+1}",
                    value=f"{user.name} (`{user_id}`)",
                    inline=False
                )
            except:
                embed.add_field(
                    name=f"User {i+1}",
                    value=f"Unknown User (`{user_id}`)",
                    inline=False
                )

        log_command(ctx, "listusers")
        await ctx.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error listing authorized users: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="stats", help="Show KeyAuth stats")
async def stats(ctx):
    if not is_authorized(ctx):
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ You are not authorized to use this command.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    try:
        params = {
            'type': 'stats'
        }

        response = make_keyauth_request(params)
        log_command(ctx, "stats")

        try:
            data = json.loads(response)
            embed = discord.Embed(
                title="KeyAuth Statistics",
                color=COLORS['info']
            )

            # Add all statistics to the embed
            for stat, value in data.items():
                embed.add_field(name=stat.capitalize(), value=value, inline=True)

            await ctx.send(embed=embed)
        except json.JSONDecodeError:
            embed = discord.Embed(
                title="Statistics Error",
                description=f"❌ Failed to get stats: {response}",
                color=COLORS['error']
            )
            await ctx.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error getting stats: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="extendkey", help="Extend a license key's duration")
async def extendkey(ctx, key: str, days: int):
    if not is_authorized(ctx):
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ You are not authorized to use this command.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    if days <= 0:
        embed = discord.Embed(
            title="Invalid Parameter",
            description="⚠️ Days must be a positive number.",
            color=COLORS['warning']
        )
        await ctx.send(embed=embed)
        return

    try:
        params = {
            'type': 'extend',
            'key': key,
            'expiry': days
        }

        response = make_keyauth_request(params)
        log_command(ctx, "extendkey", f"Key: {key}, Days: {days}")

        if "success" in response.lower():
            embed = discord.Embed(
                title="Key Extended",
                description=f"✅ Successfully extended key `{key}` by {days} day(s).",
                color=COLORS['success']
            )
        else:
            embed = discord.Embed(
                title="Extension Failed",
                description=f"❌ Failed to extend key: {response}",
                color=COLORS['error']
            )

        await ctx.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error extending key: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="setuphwid", help="Set up HWID reset for customers")
async def setuphwid(ctx):
    if not is_authorized(ctx):
        embed = discord.Embed(
            title="Access Denied",
            description="⛔ You are not authorized to use this command.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        return

    try:
        # Create an embed with instructions
        embed = discord.Embed(
            title="🔑 HWID Reset Service",
            description="Customers can reset their HWID once every 3 days using the button below.",
            color=COLORS['info']
        )

        embed.add_field(
            name="Instructions", 
            value="1. Click the 'Reset HWID' button below\n"
                  "2. Enter your license key in the popup\n"
                  "3. Your HWID will be reset if you meet the requirements", 
            inline=False
        )

        embed.add_field(
            name="Requirements",
            value=f"• You must have the Customer role <@&{CUSTOMER_ROLE_ID}>\n"
                  f"• You can only reset your HWID once every {HWID_COOLDOWN_DAYS} days",
            inline=False
        )

        embed.set_footer(text="Pulse License Manager")

        # Create the view with the button
        view = KeyAuthView(bot)

        # Send the message with the button
        await ctx.send(embed=embed, view=view)

        log_command(ctx, "setuphwid")

    except Exception as e:
        embed = discord.Embed(
            title="Error",
            description=f"❌ Error setting up HWID reset: {str(e)}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)

@bot.command(name="commands", help="Show all available commands")
async def commands_list(ctx):
    embed = discord.Embed(
        title="🔑 Pulse KeyAuth License Manager",
        description="Your powerful license management solution",
        color=discord.Color.blurple()
    )

    embed.set_thumbnail(url="https://cdn3.iconfinder.com/data/icons/security-105/100/security_key_lock_password_access_protection_unlock-512.png")

    embed.add_field(
        name="ℹ️ Basic Commands",
        value="```\n"
              f"{PREFIX}ping - Check bot status\n"
              f"{PREFIX}verifykey - Verify a license key\n"
              f"{PREFIX}commands - Show this menu\n"
              "```",
        inline=False
    )

    if is_authorized(ctx):
        embed.add_field(
            name="🔑 License Management",
            value="```\n"
                  f"{PREFIX}genkey - Generate new keys\n"
                  f"{PREFIX}deletekey - Remove a key\n"
                  f"{PREFIX}resethwid - Reset key HWID\n"
                  f"{PREFIX}keyinfo - View key details\n"
                  f"{PREFIX}bankey - Ban a license key\n"
                  f"{PREFIX}unbankey - Unban a key\n"
                  f"{PREFIX}extendkey - Extend duration\n"
                  "```",
            inline=False
        )

        embed.add_field(
            name="👤 User Management",
            value="```\n"
                  f"{PREFIX}adduser - Add admin user\n"
                  f"{PREFIX}removeuser - Remove admin\n"
                  f"{PREFIX}listusers - List admins\n"
                  "```",
            inline=False
        )

        embed.add_field(
            name="📊 Analytics",
            value=f"```\n{PREFIX}stats - View statistics\n```",
            inline=False
        )

        embed.add_field(
            name="🔧 Setup",
            value=f"```\n{PREFIX}setuphwid - Create HWID reset interface\n```",
            inline=False
        )

    embed.set_footer(
        text=f"Requested by {ctx.author.name}",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else None
    )

    log_command(ctx, "commands")
    await ctx.send(embed=embed)

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(
            title="Command Not Found",
            description=f"❌ Command not found. Use {PREFIX}commands for a list of commands.",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="Missing Argument",
            description=f"❌ Missing required argument: {error.param}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="Bad Argument",
            description=f"❌ Bad argument: {error}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="Error",
            description=f"❌ An error occurred: {error}",
            color=COLORS['error']
        )
        await ctx.send(embed=embed)
        print(f"Error: {error}")

# Load authorized users from file if it exists
def load_authorized_users():
    global AUTHORIZED_USERS
    try:
        if os.path.exists("authorized_users.json"):
            with open("authorized_users.json", "r") as file:
                AUTHORIZED_USERS = json.load(file)
    except Exception as e:
        print(f"Error loading authorized users: {e}")

# Run bot
if __name__ == "__main__":
    print("Starting KeyAuth Bot...")
    load_authorized_users()
    bot.run(TOKEN)
