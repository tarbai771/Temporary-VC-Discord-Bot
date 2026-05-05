import discord
from discord.ext import commands
from discord import app_commands
import logging
from dotenv import load_dotenv
import os
import json

# Loading the config files
def load_all_configs():
    """Reads the JSON file. Returns an empty dict if the file doesn't exist."""
    if not os.path.exists("config.json"):
        return {}
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

# Saving config files
def save_config(guild_id, hub_id, cat_id):
    """Updates the JSON file with new IDs for a specific server."""
    data = load_all_configs()
    # We use str(guild_id) because JSON keys must be strings
    data[str(guild_id)] = {
        "hub_id": hub_id, 
        "cat_id": cat_id
    }
    with open("config.json", "w") as f:
        json.dump(data, f, indent=4)

# Getting Discord Token
load_dotenv()
token = os.getenv('DISCORD_TOKEN')

# Creating a Log/Console File
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")

# Discord bot Intents(Permissions)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True  # Required to detect VC joins/leaves
intents.guilds = True        # Required to manage channels

# Bot command prefix
bot = commands.Bot(command_prefix="/", intents=intents)

# On ready Event
@bot.event
async def on_ready():
    bot.add_view(VoiceControlView())
    print(f'Logged in as {bot.user.name}')

    # Cleans all the Ghost channels when bot restarts
    configs = load_all_configs()
    
    for guild in bot.guilds:
        guild_id = str(guild.id)
        if guild_id in configs:
            cat_id = configs[guild_id].get("cat_id")
            hub_id = configs[guild_id].get("hub_id")
            
            category = guild.get_channel(cat_id)
            if category:
                for channel in category.voice_channels:
                    # Don't delete the Hub!
                    if channel.id == hub_id:
                        continue
                    
                    # If the channel is empty, delete it
                    if len(channel.members) == 0:
                        try:
                            await channel.delete(reason="Cleanup: Ghost channel found on startup.")
                            print(f"🧹 Cleaned up ghost channel: {channel.name}")
                        except discord.Forbidden:
                            print(f"❌ No permission to delete {channel.name}")
                        except discord.NotFound:
                            pass

# /setup command
@bot.tree.command(name="setup", description="Set the Hub channel and Category for temporary VCs")
@app_commands.checks.has_permissions(administrator=True) # Allow only Admins to run /setup command
async def setup(interaction: discord.Interaction):
    guild = interaction.guild
    category_name = "Temporary Channels"
    hub_name = "➕ Join to Create"

    # 1. Check if the Category exists,If not then it creates one
    category = discord.utils.get(guild.categories, name=category_name)
    if category is None:
        category = await guild.create_category(category_name)
        status_cat = f"✅ Created Category: **{category_name}**"
    else:
        status_cat = f"ℹ️ Category **{category_name}** already exists."

    # 2. Check if the Hub Channel exists inside that category, If not then it creates one
    hub_channel = discord.utils.get(category.voice_channels, name=hub_name)
    if hub_channel is None:
        hub_channel = await guild.create_voice_channel(
            hub_name,
            category=category,
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True), # Allows everyone to join
                guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True) #Allows Bot the control to this channel
            })
        status_hub = f"✅ Created Hub: **{hub_name}**"
    else:
        status_hub = f"ℹ️ Hub **{hub_name}** already exists."

    # Final report to the user
    await interaction.response.send_message(f"{status_cat}\n{status_hub}", ephemeral=True)

    # Saving to a config file
    try:
        save_config(guild.id, hub_channel.id, category.id)
        await interaction.response.send_message(
            f"✅ System ready and saved!\n**Category ID:** `{category.id}`\n**Hub ID:** `{hub_channel.id}`", 
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to save config: {e}", ephemeral=True)

# Creating Temp VC
@bot.event
async def on_voice_state_update(member, before, after):
    # 1. Loading Category and Hub ID
    configs = load_all_configs()

    # We convert the ID to a string because JSON keys are always strings
    guild_id = str(member.guild.id)
    guild_data = configs.get(guild_id)

    # check if setup is done
    if not guild_data:
        return
    
    # passing IDs
    hub_id = guild_data.get("hub_id")
    cat_id = guild_data.get("cat_id")

    # 2. Check if user joined the "Join to Create" Hub
    if after.channel and after.channel.id == hub_id:
        guild = member.guild
        category = guild.get_channel(cat_id)

        # Create the new voice channel
        new_channel = await guild.create_voice_channel(
            name=f"{member.display_name}'s Room",
            category=category,
            overwrites={
                member.guild.default_role: discord.PermissionOverwrite(connect=True), # Open for everyone
                member: discord.PermissionOverwrite(connect=True, manage_channels=True) # Full control for the owner
            }
        )

        await member.move_to(new_channel) # Move the member to the new channel

        # NEW: Send the interface message
        embed = discord.Embed(
            title="Voice Control Panel",
            description="Use the buttons below to manage your temporary channel.",
            color=discord.Color.blue()
        )
        await new_channel.send(content=f"Welcome {member.mention}!", embed=embed, view=VoiceControlView())

    # 3. Cleanup: Check if the channel the user left was a temp channel
    if before.channel:
        # Check: Is this channel inside our designated Temp Category?
        if before.channel.category_id == cat_id:
            # Safety: Make sure we aren't deleting the Hub channel itself
            if before.channel.id != hub_id:
                # If the channel is now empty, delete it
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete(reason="Temporary channel empty.")
                    except discord.NotFound:
                        # Channel already deleted by the Delete Button
                        pass
                    except discord.Forbidden:
                        print(f"❌ Missing Permissions to delete channel in {member.guild.name}")

# This Shows a list of users that we can use in our interface for stuff like kick, mute, ban etc.
class UniversalMemberSelect(discord.ui.Select):
    def __init__(self, members, action_func, placeholder):
        # We store the function we want to run later
        self.action_func = action_func
        
        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id)) 
            for m in members if not m.bot
        ]
        
        super().__init__(placeholder=placeholder, options=options)

    async def callback(self, interaction: discord.Interaction):
        # Get the selected member
        member_id = int(self.values[0])
        member = interaction.guild.get_member(member_id)
        
        # Run the specific function we passed in!
        await self.action_func(interaction, member)

class UniversalSelectView(discord.ui.View):
    def __init__(self, members, action_func, placeholder="Select a member..."):
        super().__init__(timeout=60)
        self.add_item(UniversalMemberSelect(members, action_func, placeholder))

# Rename Interface
class RenameModal(discord.ui.Modal, title="Rename Your Channel"):
    # This is the text box in the pop-up
    new_name = discord.ui.TextInput(
        label="Channel Name",
        placeholder="Enter new name (e.g. Chill Zone)",
        min_length=1,
        max_length=25
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Check if the user is in the voice channel they are trying to rename
        if interaction.user.voice and interaction.user.voice.channel:
            channel = interaction.user.voice.channel
            await channel.edit(name=f"🔊 {self.new_name.value}")
            await interaction.response.send_message(f"✅ Channel renamed to: **{self.new_name.value}**", ephemeral=True)
        else:
            await interaction.response.send_message("❌ You must be in the voice channel to rename it!", ephemeral=True)

# Limit Button Interface
class LimitModal(discord.ui.Modal, title="Set User Limit"):
    # Text input for the number
    user_limit = discord.ui.TextInput(
        label="User Limit (0 to 99)",
        placeholder="0 = Unlimited, 99 = Max",
        min_length=1,
        max_length=2,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.voice and interaction.user.voice.channel:
            channel = interaction.user.voice.channel
            
            # Validation: Ensure the input is a number
            try:
                limit_value = int(self.user_limit.value)
                if 0 <= limit_value <= 99:
                    await channel.edit(user_limit=limit_value)
                    status = "unlimited" if limit_value == 0 else f"{limit_value} users"
                    await interaction.response.send_message(f"✅ Channel limit set to **{status}**.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Please enter a number between 0 and 99.", ephemeral=True)
            except ValueError:
                await interaction.response.send_message("❌ Invalid input. Please enter a number.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ You must be in the voice channel to change the limit!", ephemeral=True)

# Kick button
@staticmethod
async def kick_action(interaction, member):
    channel = interaction.user.voice.channel
    await member.move_to(None)
    await channel.set_permissions(member, connect=False)
    await interaction.response.edit_message(content=f"👢 Kicked **{member.display_name}**", view=None)

# Ownership Transfer
@staticmethod
async def transfer_action(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.user.voice.channel
    
    # 1. Update the channel name to reflect the new owner
    try:
        await channel.edit(name=f"🔊 {member.display_name}'s Room")
        
        # 2. Update permissions: Give the new owner 'Manage Channels' 
        # and remove it from the old owner if you want a total transfer
        await channel.set_permissions(member, connect=True, manage_channels=True, move_members=True)
        await channel.set_permissions(interaction.user, connect=True, manage_channels=False)
        
        await interaction.response.edit_message(
            content=f"👑 Ownership transferred to **{member.display_name}**!", 
            view=None
        )
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to rename this channel.", ephemeral=True)

# Interface
class VoiceControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Persistent view

    # --- HELPER: SECURITY CHECK ---
    def is_owner(self, interaction: discord.Interaction):
        """Checks if the user is the current rightful owner of the VC."""
        # Check 1: Does their name match the channel name?
        name_match = interaction.user.display_name.lower() in interaction.channel.name.lower()
        # Check 2: Do they have 'Manage Channels' (granted by Transfer button)?
        has_perm = interaction.channel.permissions_for(interaction.user).manage_channels
        
        return name_match or has_perm

    # Lock Button
    @discord.ui.button(label="Lock", style=discord.ButtonStyle.danger, custom_id="lock_vc")
    async def lock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only allow the owner to control VC
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the current owner can lock the room!", ephemeral=True)
            
        await interaction.channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("🔒 Room locked!", ephemeral=True)

    # Unlock Button
    @discord.ui.button(label="Unlock", style=discord.ButtonStyle.success, custom_id="unlock_vc")
    async def unlock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the current owner can unlock the room!", ephemeral=True)
            
        await interaction.channel.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message("🔓 Room unlocked!", ephemeral=True)

    # Rename Button
    @discord.ui.button(label="Rename", style=discord.ButtonStyle.secondary, custom_id="rename_vc")
    async def rename_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the current owner can rename this room!", ephemeral=True)
            
        await interaction.response.send_modal(RenameModal())

    # Limit Button
    @discord.ui.button(label="Set Limit", style=discord.ButtonStyle.primary, custom_id="limit_vc")
    async def limit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the current owner can set limits!", ephemeral=True)
            
        await interaction.response.send_modal(LimitModal())

    # Delete Button
    @discord.ui.button(label="Delete Room", style=discord.ButtonStyle.danger, custom_id="delete_vc")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the current owner can delete this room!", ephemeral=True)

        data = load_all_configs()
        guild_data = data.get(str(interaction.guild.id))
        
        if guild_data and interaction.channel.category_id == guild_data.get("cat_id"):
            await interaction.response.send_message("💥 Deleting channel...", ephemeral=True)
            await interaction.channel.delete(reason="Owner requested deletion via button.")
        else:
            await interaction.response.send_message("⚠️ Error: This is not a temporary channel.", ephemeral=True)

    # Kick Button
    @discord.ui.button(label="Kick", style=discord.ButtonStyle.secondary, custom_id="kick_vc")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the owner can kick members!", ephemeral=True)
            
        members = [m for m in interaction.channel.members if m != interaction.user and not m.bot]
        if not members:
            return await interaction.response.send_message("No one else is here!", ephemeral=True)
        
        view = UniversalSelectView(members, kick_action, "Who should be kicked?")
        await interaction.response.send_message("Select a member:", view=view, ephemeral=True)

    # Ownership transfer
    @discord.ui.button(label="Transfer Owner", style=discord.ButtonStyle.primary, emoji="👑", custom_id="transfer_vc")
    async def transfer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the current owner can transfer ownership!", ephemeral=True)

        members = [m for m in interaction.channel.members if m != interaction.user and not m.bot]
        if not members:
            return await interaction.response.send_message("❌ No one else is here to take ownership!", ephemeral=True)

        view = UniversalSelectView(members, transfer_action, "Pick the new owner...")
        await interaction.response.send_message("Select a member:", view=view, ephemeral=True)

# Running the Bot
bot.run(token, log_handler=handler, log_level=logging.DEBUG)