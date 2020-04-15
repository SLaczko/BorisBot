# borisbot.py
import os
import discord
import re
import random
import ResponseHandler
from discord.ext import commands

TOKEN_FILE = ".token"
BOT_PREFIX = ('<@698354966078947338>', '~', '<@!698354966078947338>', '<@&698361022712381451>')
STR_NO_RESPONSE = "Look, I'm not all that bright. \nType ~help teach and teach me some new phrases, would ya?"
botDict = 'responses.txt'
botNoResponse = "Use ~teach \"Trigger\" \"Response\" to teach me how to respond to something!"

with open(TOKEN_FILE, 'r') as tokenFile:
    TOKEN = tokenFile.read()

client = discord.Client()
bot = commands.Bot(command_prefix=BOT_PREFIX)
resHand = ResponseHandler.ResponseHandler(botDict, botNoResponse)


@bot.command(name='hi')
async def hi(ctx):
    print("Got message \'hi\'")
    greetings = ["Well howdy!",
                 "Howdy pardner!"]

    response = random.choice(greetings)
    await ctx.send(response)


@bot.command(name='plan', help='For planning on the weekend. You sir have to ping everyone, though.')
async def plan(ctx):
    print("Planning")

    msg = await ctx.send("Howdy! Les all gather up and spend some quality time together.\n"
                         "Click them emojis correspondin' to the days you're free.")
    reactions = ['🇫', '🇸', '🌞']
    # reactions_names = ["regional_indicator_f", "regional_indicator_s", "sun_with_face"]
    # for reaction in reactions_names: reactions.append(discord.utils.get(bot.emojis, name=reaction))
    print(reactions)
    for dayReaction in reactions:
        if dayReaction:
            await msg.add_reaction(dayReaction)


@bot.command(name='teach', help='Usage: ~teach \"Trigger phrase\" \"Desired response\"')
async def teach(ctx, *args):
    # take in and sanitize trigger
    iterargs = iter(args)
    trigger = str(next(iterargs))
    print("Trigger: " + trigger)
    trigger = re.sub(r'[^a-zA-Z ]', '', str(trigger).strip().lower())

    response = str(next(iterargs)) + ' '
    for arg in iterargs:
        print("Arg: " + str(arg))
        response += str(arg) + ' '
    response = response.strip()
    print("Learning to respond to \"" + trigger + "\" with \"" + response + '\"')
    await ctx.send("Learned to respond to \"" + trigger + "\" with \"" + response + '\"')

    await resHand.addResponse(botDict, trigger, response)


@bot.event
async def on_ready():
    print("Boris has connected to Discord!")


@bot.event
async def on_message(message):
    print(message.content)
    if message.author == client.user:
        return

    mentionIDList = []
    for mention in message.mentions:
        mentionIDList.append(mention.id)
    botID = bot.user.id
    if botID in mentionIDList:
        print("Boris mention DETECTED")

        # get and send response
        response = await resHand.getResponse(botDict, message)
        if response is not None:
            print("Response: " + response)
            await send_message(message.channel.id, response)
        else:
            await send_message(message.channel.id, botNoResponse)

    if message.content == 'raise-exception':
        raise discord.DiscordException

    await bot.process_commands(message)


@bot.event
async def on_member_join(member):
    send_message(658114649081774093, "<@!" + member.id + "> :gunworm:")


async def send_message(channelID, message):
    channel = bot.get_channel(channelID)
    await channel.send(message)


@bot.event
async def on_error(event, *args, **kwargs):
    with open('err.log', 'a') as f:
        if event == 'on_message':
            f.write("Unhandled message: " + str(args[0]) + "\n")
            await send_message(696863794743345152, args[1])
        else:
            raise


def sanitize_string(input):
    return re.sub(r'[^a-zA-Z ]', '', str(input).strip().lower())


bot.run(TOKEN)