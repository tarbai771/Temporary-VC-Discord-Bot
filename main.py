import discord
from discord.ext import commands
from discord import app_commands
import logging
from dotenv import load_dotenv
import os
import json

def load_all_configs():
    """Reads the JSON file. Returns an empty dict if the file doesn't exist."""
    if not os.path.exists("config.json"):
        return {}
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

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

# Tracking created channels
temp_channels = []

@bot.event
async def on_ready():
    bot.add_view(VoiceControlView())
    await bot.tree.sync()
    print("Commands synced!")
    print(f'Logged in as {bot.user.name}')

# /setup command
@bot.tree.command(name="setup", description="Set the Hub channel and Category for temporary VCs")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    guild = interaction.guild
    category_name = "Temporary Channels"
    hub_name = "➕ Join to Create"

    # 1. Check if the Category exists
    category = discord.utils.get(guild.categories, name=category_name)
    if category is None:
        category = await guild.create_category(category_name)
        status_cat = f"✅ Created Category: **{category_name}**"
    else:
        status_cat = f"ℹ️ Category **{category_name}** already exists."

    # 2. Check if the Hub Channel exists inside that category
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
        temp_channels.append(new_channel.id) # Add to our tracking list

        # NEW: Send the interface message
        embed = discord.Embed(
            title="Voice Control Panel",
            description="Use the buttons below to manage your temporary channel.",
            color=discord.Color.blue()
        )
        await new_channel.send(content=f"Welcome {member.mention}!", embed=embed, view=VoiceControlView())

    # 3. Cleanup: Check if the channel the user left was a temp channel
    if before.channel and before.channel.id in temp_channels:
        # If the channel is now empty, delete it
        if len(before.channel.members) == 0:
            await before.channel.delete()
            temp_channels.remove(before.channel.id)

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

# Interface
class VoiceControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Persistent view

    # Lock Button
    @discord.ui.button(label="Lock", style=discord.ButtonStyle.danger, custom_id="lock_vc")
    async def lock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only allow the person in the VC to control it
        if interaction.user.voice and interaction.user.voice.channel:
            await interaction.user.voice.channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("🔒 Room locked!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ You must be in the VC to lock it.", ephemeral=True)

    # Unlock Button
    @discord.ui.button(label="Unlock", style=discord.ButtonStyle.success, custom_id="unlock_vc")
    async def unlock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.voice and interaction.user.voice.channel:
            await interaction.user.voice.channel.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.response.send_message("🔓 Room unlocked!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ You must be in the VC to unlock it.", ephemeral=True)

    # Rename Button
    @discord.ui.button(label="Rename", style=discord.ButtonStyle.secondary, custom_id="rename_vc")
    async def rename_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Instead of sending a message, we send the Modal pop-up
        await interaction.response.send_modal(RenameModal())

    # Limit Button
    @discord.ui.button(label="Set Limit", style=discord.ButtonStyle.primary, custom_id="limit_vc")
    async def limit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Open the Limit Modal
        await interaction.response.send_modal(LimitModal())

# Running the Bot
bot.run(token, log_handler=handler, log_level=logging.DEBUG)