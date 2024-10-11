import os

import discord

intents = discord.Intents.default()
intents.members = True  # This is necessary to access the list of members
print(os.getenv('DISCORD_TOKEN'))
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Logged in as {client.user}!')

    guild = discord.utils.get(client.guilds, name="Brawlerz - Community")
    if guild is None:
        print("Server not found!")
        return

    print("Available Roles:")
    for role in guild.roles:
        print(role.name)

    # Ask for the role name to list members
    role_name = input("Enter the role name to print its members: ")
    role = discord.utils.get(guild.roles, name=role_name)

    if role is None:
        print(f"No role named '{role_name}' found in this server.")
        return

    print(f"Members with the role '{role_name}':")
    for member in guild.members:
        if role in member.roles:
            print(f"{member.name}#{member.discriminator}")

    # Close the client after the task is done
    await client.close()

client.run(str(os.getenv('DISCORD_TOKEN')))
