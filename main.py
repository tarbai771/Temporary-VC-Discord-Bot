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

    # Syncing commands with discord globally
    # It may take 1 hour for commands to appear when you first sync the commands
    try:
        synced = await bot.tree.sync()
        print(f"Successfully synced {len(synced)} commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

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
    # Loading Category and Hub ID
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

    # Check if user joined the "Join to Create" Hub
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

        # Send the interface message
        embed = discord.Embed(
            title="Voice Control Panel",
            description="Use the buttons below to manage your temporary channel.",
            color=discord.Color.default()
        )
        file = discord.File("mist_interface.png", filename="mist_interface.png")
        embed.set_image(url="attachment://mist_interface.png")

        await new_channel.send(content=f"Welcome {member.mention}!", embed=embed, file=file, view=VoiceControlView())

    # Cleanup: Check if the channel the user left was a temp channel
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

# This Shows a drop-down list of users that are in the voice channel
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

# Privacy Button Interface
class PrivacySelectView(discord.ui.View):
    def __init__(self, owner_check_func):
        super().__init__(timeout=60)
        self.is_owner = owner_check_func # Pass the owner check logic from the main view

    @discord.ui.select(
        placeholder="🛡️ Choose a Privacy Option...",
        options=[
            discord.SelectOption(label="Lock Room", value="lock", emoji="🔒"),
            discord.SelectOption(label="Unlock Room", value="unlock", emoji="🔓"),
            discord.SelectOption(label="Invisible (Trusted Only)", value="invisible", emoji="👻"),
            discord.SelectOption(label="Visible (Everyone)", value="visible", emoji="👁️"),
            discord.SelectOption(label="Close Chat", value="close_chat", emoji="💬", description="Only Trusted users can type."),
            discord.SelectOption(label="Enable Chat", value="show_chat", emoji="💬"),
            discord.SelectOption(label="Disable Chat", value="disable_chat", emoji="🔇", description="No one can type.")
        ]
    )
    async def privacy_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the owner can do this!", ephemeral=True)

        choice = select.values[0]
        channel = interaction.channel
        everyone = interaction.guild.default_role
        owner = interaction.user

        # 1. Preserve current settings
        current_everyone_overwrites = channel.overwrites_for(everyone)
        
        # 2. Ensure Owner and Bot don't lose access
        await channel.set_permissions(owner, view_channel=True, connect=True, send_messages=True)

        if choice == "lock":
            current_everyone_overwrites.connect = False
            msg = "🔒 Room locked! New people cannot join."
        
        elif choice == "unlock":
            current_everyone_overwrites.connect = True
            msg = "🔓 Room unlocked!"

        elif choice == "invisible":
            current_everyone_overwrites.view_channel = False
            msg = "👻 Room is now invisible to everyone except Trusted users!"

        elif choice == "visible":
            current_everyone_overwrites.view_channel = True
            msg = "👁️ Room is now visible to everyone."

        elif choice == "close_chat":
            # We set @everyone to False. 
            # Trusted users can still type because their personal override is True.
            current_everyone_overwrites.send_messages = False
            msg = "🔒💬 Chat is now CLOSED. Only Trusted users and the owner can type!"

            # Reset Trusted Users to TRUE so they can bypass the @everyone mute
            for target, overwrite in channel.overwrites.items():
                if isinstance(target, discord.Member) and target != owner:
                    # If they have 'Connect' allowed, they are a trusted user
                    if overwrite.connect is True:
                        overwrite.send_messages = True
                        await channel.set_permissions(target, overwrite=overwrite)

        elif choice == "show_chat":
            current_everyone_overwrites.send_messages = True
            msg = "💬 Chat enabled!"

            # Reset Trusted Users to NONE (Default) 
            # This makes them follow the @everyone 'True' setting again
            for target, overwrite in channel.overwrites.items():
                if isinstance(target, discord.Member) and target != owner:
                    overwrite.send_messages = None 
                    await channel.set_permissions(target, overwrite=overwrite)

        elif choice == "disable_chat":
            current_everyone_overwrites.send_messages = False
            msg = "🔇 Chat disabled!"

            # Set every Trusted User to False so they are muted too
            for target, overwrite in channel.overwrites.items():
                if isinstance(target, discord.Member) and target != owner:
                    overwrite.send_messages = False
                    await channel.set_permissions(target, overwrite=overwrite)

        # 3. Apply changes to @everyone
        await channel.set_permissions(everyone, overwrite=current_everyone_overwrites)

        await interaction.response.edit_message(content=msg, view=None)

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

# Invite Button Interface
class InviteResponseView(discord.ui.View):
    def __init__(self, target_member: discord.Member, destination_channel: discord.VoiceChannel):
        super().__init__(timeout=300) # 5 minute expiry
        self.target_member = target_member
        self.destination_channel = destination_channel

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Verify the person clicking is the person invited
        if interaction.user != self.target_member:
            return await interaction.response.send_message("This invite isn't for you!", ephemeral=True)

        # 2. Check if they are actually in a voice channel to be "dragged"
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ You must be in a voice channel first so I can move you!", ephemeral=True)

        # 3. Move them
        try:
            await interaction.user.move_to(self.destination_channel)
            await interaction.response.edit_message(content=f"✅ {interaction.user.mention} has joined the room!", view=None)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to move you!", ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.target_member:
            return await interaction.response.send_message("This invite isn't for you!", ephemeral=True)
            
        await interaction.response.edit_message(content=f"❌ {interaction.user.mention} declined the invite.", view=None)

# Invite action
async def invite_action(interaction: discord.Interaction, member: discord.Member):
    # The channel the owner is currently in
    channel = interaction.channel
    
    # Check if the target is already in the VC
    if member in channel.members:
        return await interaction.response.send_message(f"{member.display_name} is already here!", ephemeral=True)

    # Send the interactive invite
    view = InviteResponseView(target_member=member, destination_channel=channel)
    
    # We send this to the channel where the owner clicked the button
    await interaction.response.edit_message(content=f"Inviting {member.mention}...", view=None)
    await interaction.channel.send(
        content=f"Hey {member.mention}! **{interaction.user.display_name}** has invited you to join their voice channel.",
        view=view
    )

# Kick action
@staticmethod
async def kick_action(interaction, member):
    channel = interaction.user.voice.channel
    await member.move_to(None)
    await channel.set_permissions(member, connect=False)
    await interaction.response.edit_message(content=f"👢 Kicked **{member.display_name}**", view=None)

# trust action
async def trust_action(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    
    # Give the user explicit 'Connect' permissions
    # This bypasses the @everyone 'Connect: False' lock
    await channel.set_permissions(member, connect=True, send_messages=True)

    await interaction.response.edit_message(
        content=f"⭐ **{member.display_name}** is now a Trusted User and can join even when locked!", 
        view=None
    )

# Untrust action
async def untrust_action(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    
    # Setting the overwrite to None, So removes the user-specific 'Trust'
    await channel.set_permissions(member, overwrite=None)

    await interaction.response.edit_message(
        content=f"🤝 **{member.display_name}** is no longer a Trusted User.", 
        view=None
    )

# Ownership Transfer action
@staticmethod
async def transfer_action(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.user.voice.channel
    
    # Update the channel name to the new owner name
    try:
        await channel.edit(name=f"🔊 {member.display_name}'s Room")
        
        # Update permissions: Give the new owner 'Manage Channels' and remove it from the old owner
        await channel.set_permissions(member, connect=True, manage_channels=True, move_members=True)
        await channel.set_permissions(interaction.user, connect=True, manage_channels=False)
        
        await interaction.response.edit_message(
            content=f"👑 Ownership transferred to **{member.display_name}**!", 
            view=None
        )
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to rename this channel.", ephemeral=True)

# Block Action
async def block_action(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    
    # Prevent the owner from blocking themselves
    if member == interaction.user:
        return await interaction.response.send_message("❌ You can't block yourself!", ephemeral=True)

    # Set the 'Connect' permission to False for this specific member
    await channel.set_permissions(member, connect=False)
    
    # If they are currently in the VC, kick them out so the block takes effect
    if member in channel.members:
        await member.move_to(None)

    await interaction.response.edit_message(
        content=f"🚫 **{member.display_name}** has been blocked from this room.", 
        view=None
    )

# Unblock Action
async def unblock_action(interaction: discord.Interaction, member: discord.Member):
    # Removing the overwrite allows them to join again
    await interaction.channel.set_permissions(member, overwrite=None)
    await interaction.response.edit_message(content=f"✅ **{member.display_name}** is now unblocked.", view=None)

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
        # Since we have rename feature, Check 1 can fail sometimes. That's why we also need check 2
        has_perm = interaction.channel.permissions_for(interaction.user).manage_channels
        
        return name_match or has_perm

    # Rename Button
    @discord.ui.button(emoji="<:rename2:1502664105478066288>", style=discord.ButtonStyle.gray, custom_id="rename_vc")
    async def rename_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the current owner can rename this room!", ephemeral=True)
            
        await interaction.response.send_modal(RenameModal())

    # Limit Button
    @discord.ui.button(emoji="<:limit2:1502664062163488829>", style=discord.ButtonStyle.gray, custom_id="limit_vc")
    async def limit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the current owner can set limits!", ephemeral=True)
            
        await interaction.response.send_modal(LimitModal())

    # Privacy Dropdown Menu
    @discord.ui.button(emoji="<:privacy2:1502664084028653628>", style=discord.ButtonStyle.gray, custom_id="privacy_menu_btn")
    async def privacy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the owner can change privacy!", ephemeral=True)
        
        # We pass self.is_owner so the sub-menu can still verify the user
        view = PrivacySelectView(self.is_owner)
        await interaction.response.send_message("Select a privacy setting:", view=view, ephemeral=True)

    # Delete Button
    @discord.ui.button(emoji="<:delete2:1502663989727854742>", style=discord.ButtonStyle.gray, custom_id="delete_vc")
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

    # Trust Button
    @discord.ui.button(emoji="<:trust2:1502664171408593036>", style=discord.ButtonStyle.gray, custom_id="trust_user_btn")
    async def trust_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the owner can trust users!", ephemeral=True)

        # Get all members (excluding bots and the owner)
        members = [m for m in interaction.guild.members if not m.bot and m != interaction.user]
        
        if not members:
            return await interaction.response.send_message("No users found to trust.", ephemeral=True)

        view = UniversalSelectView(members, trust_action, "Who should be a Trusted User?")
        await interaction.response.send_message("Select a user to trust:", view=view, ephemeral=True)

    # Untrust Button
    @discord.ui.button(emoji="<:untrust2:1502664216505614407>", style=discord.ButtonStyle.gray, custom_id="untrust_user_btn")
    async def untrust_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the owner can manage trusted users!", ephemeral=True)

        # Find users who have specific overwrites in this channel
        trusted_members = []
        for target, overwrite in interaction.channel.overwrites.items():
            # Check if the target is a Member and has Connect allowed
            if isinstance(target, discord.Member) and overwrite.connect is True:
                # We skip the owner and bots
                if target != interaction.user and not target.bot:
                    trusted_members.append(target)

        if not trusted_members:
            return await interaction.response.send_message("There are no trusted users to remove.", ephemeral=True)

        view = UniversalSelectView(trusted_members, untrust_action, "Who should lose Trusted status?")
        await interaction.response.send_message("Select a user to untrust:", view=view, ephemeral=True)

    # invite Button
    @discord.ui.button(emoji="<:invite2:1502664016642969670>", style=discord.ButtonStyle.gray, custom_id="invite_user_btn")
    async def invite_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the owner can invite users!", ephemeral=True)

        # Get all members except bots and the owner themselves
        members = [m for m in interaction.guild.members if not m.bot and m != interaction.user]
        
        if not members:
            return await interaction.response.send_message("No users found to invite.", ephemeral=True)

        # Reusing your UniversalSelectView
        view = UniversalSelectView(members, invite_action, "Who would you like to invite?")
        await interaction.response.send_message("Select a user to invite:", view=view, ephemeral=True)

    # Kick Button
    @discord.ui.button(emoji="<:kick2:1502664039250137168>", style=discord.ButtonStyle.gray, custom_id="kick_vc")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the owner can kick members!", ephemeral=True)
            
        members = [m for m in interaction.channel.members if m != interaction.user and not m.bot]
        if not members:
            return await interaction.response.send_message("No one else is here!", ephemeral=True)
        
        view = UniversalSelectView(members, kick_action, "Who should be kicked?")
        await interaction.response.send_message("Select a member:", view=view, ephemeral=True)

    # Block Button
    @discord.ui.button(emoji="<:block2:1502663918311440566>", style=discord.ButtonStyle.gray, custom_id="block_vc")
    async def block_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Your existing is_owner check
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the owner can block users!", ephemeral=True)

        # Get members in the guild to block (we can't just look in the VC, 
        # because you might want to block someone before they join!)
        # To keep the list clean, let's look at people recently active or in the VC
        members = [m for m in interaction.guild.members if not m.bot and m != interaction.user]
        
        # NOTE: If your server is huge, you might want to only show people 
        # currently in the VC to keep the dropdown short:
        # members = [m for m in interaction.channel.members if m != interaction.user]

        if not members:
            return await interaction.response.send_message("No one found to block.", ephemeral=True)

        view = UniversalSelectView(members, block_action, "Who should be blocked from joining?")
        await interaction.response.send_message("Select a member to block:", view=view, ephemeral=True)

    # Unblock Button
    @discord.ui.button(emoji="<:unblock2:1502664195882352731>", style=discord.ButtonStyle.gray, custom_id="unblock_vc")
    async def unblock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_owner(interaction):
            return await interaction.response.send_message("⚠️ Only the owner can unblock users!", ephemeral=True)

        # Look for members who currently have a 'connect=False' overwrite
        blocked_members = []
        for target, overwrite in interaction.channel.overwrites.items():
            if isinstance(target, discord.Member) and overwrite.connect is False:
                blocked_members.append(target)

        if not blocked_members:
            return await interaction.response.send_message("No one is currently blocked.", ephemeral=True)

        view = UniversalSelectView(blocked_members, unblock_action, "Who should be unblocked?")
        await interaction.response.send_message("Select a member to unblock:", view=view, ephemeral=True)

    # Claim ownership button
    @discord.ui.button(emoji="<:claim2:1502663959969398921>", style=discord.ButtonStyle.gray, custom_id="claim_vc")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        
        # Verification: User must be in the VC to claim it
        if interaction.user not in channel.members:
            return await interaction.response.send_message("⚠️ You must be in the voice channel to claim it!", ephemeral=True)

        # Find the current owner
        current_owner = None
        for target, overwrite in channel.overwrites.items():
            if isinstance(target, discord.Member) and overwrite.manage_channels is True:
                current_owner = target
                break

        # Check if the owner is actually gone
        if current_owner and current_owner in channel.members:
            return await interaction.response.send_message(f"❌ The owner (**{current_owner.display_name}**) is still in the room!", ephemeral=True)

        # Remove perms from the old owner (if they exist)
        if current_owner:
            await channel.set_permissions(current_owner, overwrite=None)
        
        # Give perms to the new owner (This satisfies the 'has_perm' check)
        await channel.set_permissions(interaction.user, manage_channels=True, move_members=True, connect=True)
        
        # Update the name (This satisfies the 'name_match' check)
        try:
            await channel.edit(name=f"🔊 {interaction.user.display_name}'s Room")
        except discord.HTTPException:
            pass # Handle Discord rate limits

        await interaction.response.send_message(f"👑 **{interaction.user.display_name}** is the new owner of this room!", ephemeral=False)

    # Ownership transfer button
    @discord.ui.button(emoji="<:newowner2:1502664125711384586>", style=discord.ButtonStyle.gray, custom_id="transfer_vc")
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