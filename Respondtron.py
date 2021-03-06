from fuzzywuzzy import fuzz
import re
import sys
import discord
from discord.ext import commands
from enum import Enum, auto
import random
import pickle


class ARGS(Enum):
    WEIGHTS = "weights"
    PROB_MIN = "probMin"
    DEBUG_CHANNEL_ID = "debugChannelId"
    ENABLE_AUTO_WEIGHTS = "enableAutoWeights"


class STATES(Enum):
    NOMINAL = auto()
    AWAITING_INPUT = auto()


SPLIT_CHAR = '\t'
ADMIN_ROLE_ID = 658116626712887316
PROB_MIN_DEF = 0.7
WEIGHTS_DEF = [1.2, 0.7, 1.1, 1]
DEF_SETTINGS = {ARGS.WEIGHTS: WEIGHTS_DEF,
                ARGS.PROB_MIN: PROB_MIN_DEF,
                ARGS.DEBUG_CHANNEL_ID: None,
                ARGS.ENABLE_AUTO_WEIGHTS: False}
GOOD_VOTE = "good"
BAD_VOTE = "bad"
SETTINGS_FILE = "settings"


# TODO
# Add undo (at least to addResponse)
class Respondtron(commands.Cog):
    responseFile = ""
    botNoResponse = ""
    cmdErrorResponse = "I do believe you messed up the command there, son."
    settings = {ARGS.WEIGHTS: WEIGHTS_DEF, ARGS.PROB_MIN: PROB_MIN_DEF, ARGS.DEBUG_CHANNEL_ID: None,
                ARGS.ENABLE_AUTO_WEIGHTS: False}
    lastScores = ()
    lastRated = False

    # to prompt user when adding new response
    tempArgs = None
    state = STATES.NOMINAL

    def __init__(self, bot, responseFile, botNoResponse, args=None):
        self.bot = bot
        self.responseFile = responseFile
        self.botNoResponse = botNoResponse
        self.loadSettings(args)

        # create backup of responses
        print("Backing up response file")
        with open(self.responseFile, 'r') as responses:
            with open("backup_" + self.responseFile, 'w+') as backup:
                backup.write(responses.read())
        try:
            self.loadSettings(load_obj(SETTINGS_FILE))
        except FileNotFoundError:
            print("No settings file")

    # SETTERS

    def setWeights(self, weights):
        self.settings[ARGS.WEIGHTS] = weights

    def setAutoWeights(self, isEnabled):
        self.settings[ARGS.ENABLE_AUTO_WEIGHTS] = isEnabled

    def setProbMin(self, probMin):
        self.settings[ARGS.PROB_MIN] = probMin

    def setDebugChannel(self, id):
        self.settings[ARGS.DEBUG_CHANNEL_ID] = id

    def loadSettings(self, args):
        if args is not None:
            for iArg in args:
                if iArg in ARGS:
                    if iArg == ARGS.WEIGHTS:
                        self.setWeights(args[iArg])
                    elif iArg == ARGS.PROB_MIN:
                        self.setProbMin(args[iArg])
                    elif iArg == ARGS.DEBUG_CHANNEL_ID:
                        self.setDebugChannel(args[iArg])
                    elif iArg == ARGS.ENABLE_AUTO_WEIGHTS:
                        self.setAutoWeights(args[iArg])

    def saveSettings(self, settings, file):
        save_obj(settings, file)
        print("Saved Settings: ", settings)

    # EVENTS

    # on_message listens for incoming messages starting with an @(botname) and then responds to them
    @commands.Cog.listener()
    async def on_message(self, message):
        # add response prompt
        if self.state == STATES.AWAITING_INPUT and message.author == self.tempArgs[0]:
            if message.content == "y":
                self.addTempResponse(self.tempArgs)
                self.state = STATES.NOMINAL
                await message.channel.send("Response Learnt.")
            elif message.content == "n":
                await message.channel.send("Response addin' cancelled.")
                self.state = STATES.NOMINAL

        mentionIDList = []
        for mention in message.mentions:
            mentionIDList.append(mention.id)
        botID = self.bot.user.id
        if botID in mentionIDList:
            print(self.bot.user.name + " mention DETECTED")

            # get and send response
            response = await self.getResponse(self.responseFile, message)
            if response is not None:
                print("Response: " + response)
                await message.channel.send(response)
            else:
                await message.channel.send(self.botNoResponse)

    @commands.Cog.listener()
    async def on_error(event, *args, **kwargs):
        with open('err.log', 'a') as f:
            if event == 'on_message':
                f.write("Unhandled message: " + str(args[0]) + "\n")
                # await send_message(696863794743345152, args[0])
            else:
                raise

    # COMMANDS

    # teach
    # teach allows the bot to learn new trigger/response pairs
    @commands.command(name='teach', help='Usage: ~teach \"Trigger phrase\" \"Desired response\"')
    async def teach(self, ctx, *args):
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

        if await self.addResponse(ctx, self.responseFile, trigger, response) is False:
            await ctx.send("I've already learned that, friend!")

    @commands.command(name="setProb", help="Usage: ~setProb [0.0-1.0]\nSets the sensitivity for matching triggers.")
    async def setProbCommand(self, ctx, prob):
        if ctx.guild.get_role(ADMIN_ROLE_ID) in ctx.message.author.roles:
            await self.setProb(prob)
            return

    @commands.command(name="setWeights")
    async def setWeightCommand(self, ctx, *weights):
        if ctx.guild.get_role(ADMIN_ROLE_ID) in ctx.message.author.roles:
            # convert weights to floats
            floatWeights = []
            for i in range(len(weights)):
                floatWeights.append(float(weights[i].strip(", ")))

            print("Weight list: ", floatWeights)

            try:
                self.setWeights(floatWeights)
                await ctx.send("Weights set to " + str(floatWeights))
            except TypeError:
                print(sys.exc_info())
                await ctx.send("Bad input, bud. Comma separated and between 0 and 1, please.")
            return

    @commands.command(name="saveSettings")
    async def saveSettingsCommand(self, ctx):
        if ctx.guild.get_role(ADMIN_ROLE_ID) in ctx.message.author.roles:
            self.saveSettings(self.settings, SETTINGS_FILE)
            await ctx.send("Setting's saved. Turnin' the heat up. Keepin' em nice and cozy.")
            return

    @commands.command(name="rate", help="Rate Boris' response for accuracy.\nUsage: ~rate [good/bad]")
    async def rateResponse(self, ctx, rating):
        rating = str(rating).lower().strip()
        isGood = None

        # if the last response was already rated, return
        if self.lastRated:
            return

        if rating == GOOD_VOTE:
            isGood = True
        elif rating == BAD_VOTE:
            isGood = False
        else:
            await ctx.send(self.cmdErrorResponse)
            return

        self.alterWeights(isGood)
        self.lastRated = True
        await ctx.send("Response rated. Gimme time, I'm learnin'.")

    @commands.command(name="weights")
    async def weightsCommand(self, ctx):
        await ctx.send(self.settings[ARGS.WEIGHTS])

    # METHODS

    def resetState(self):
        self.state = STATES.NOMINAL
        self.tempArgs = []

    # if user vote was good, increase weight of highest string matching factor
    # if vote was bad, decrease weight of lowest string matching factor
    def alterWeights(self, isGood):
        # find the largest string matching factor
        weights = self.settings[ARGS.WEIGHTS]
        if isGood:
            largestWeight = 0
            iLargestWeight = 0
            for i in range(len(weights)):
                if weights[i] > largestWeight:
                    largestWeight = weights[i]
                    iLargestWeight = i

            # increase weight of highest string matching factor
            print("Weight index changed: ", iLargestWeight)
            print("Change from: ", weights[iLargestWeight])
            weights[iLargestWeight] += 0.1
            print("To: ", weights[iLargestWeight])

        elif not isGood:
            smallestWeight = 0
            iSmallestWeight = 0
            # find the largest string matching factor
            for i in range(len(weights)):
                if weights[i] < smallestWeight:
                    smallestWeight = weights[i]
                    iSmallestWeight = i

            # lower weight of lowest string matching factor
            print("Weight index changed: ", iSmallestWeight)
            print("Change from: ", weights[iSmallestWeight])
            weights[iSmallestWeight] -= 0.1
            print("To: ", weights[iSmallestWeight])

        self.settings[ARGS.WEIGHTS] = weights

    async def addResponse(self, ctx, responseFile, newTrigger, newResponse):
        triggerMatch = False
        duplicate = False
        matchedTrigger = ""
        with open(responseFile, 'r') as responses:
            lines = responses.readlines()

        for i in range(len(lines)):  # iterate through triggers and responses
            entries = lines[i].split(SPLIT_CHAR)
            trigger = entries[0]

            # TODO Make this find all matches and choose the highest probability
            # if the trigger is already present, add new response to trigger
            matchArgs = await self.botMatchString(trigger, newTrigger)
            if matchArgs[0]:
                for response in entries:  # skip if response is already present
                    if newResponse.lower().strip() == response.lower().strip():
                        duplicate = True

                triggerMatch = True
                if not duplicate:
                    matchedTrigger = trigger
                    lines[i] = lines[i].strip()
                    lines[i] += SPLIT_CHAR + newResponse

        # Adding Response

        if duplicate:
            print("Duplicate Response. Not adding.")
            return False

        # Add response to existing trigger
        elif triggerMatch:
            self.prepPrompt(ctx.message.author, lines)
            await ctx.send("Adding response to existing trigger \"" + matchedTrigger + "\"\nIs this correct? (y/n)")
            return True
        # if the trigger was not in the file before, make a new trigger+response
        else:
            self.prepPrompt(ctx.message.author, newTrigger, newResponse)
            await ctx.send("Adding new trigger/response \"" + newTrigger + "\"/\"" + newResponse + "\"\nIs this correct? (y/n)")
            return True

    def prepPrompt(self, *args):
        self.tempArgs = []
        for arg in args:
            self.tempArgs.append(arg)
        self.state = STATES.AWAITING_INPUT

    def addTempResponse(self, args):
        if len(args) == 3:
            newTrigger = args[1]
            newResponse = args[2]
            with open(self.responseFile, 'a') as responses:
                print("Adding new trigger/response.\n Trigger: ", newTrigger)
                responses.write(newTrigger + SPLIT_CHAR + newResponse)

        elif len(args) == 2:
            lines = self.tempArgs[1]
            with open(self.responseFile, 'w') as responses:
                print("Added response to existing trigger")
                responses.write(''.join(lines))

    async def getResponse(self, responseFile, message):
        # get trigger
        triggerList = str(message.content).split()[1:]
        trigger = ""
        for word in triggerList:
            trigger += word + ' '
        trigger = sanitize_string(trigger)

        # open file of responses
        with open(responseFile, 'r') as responseFile:
            lines = responseFile.readlines()

        matches = []
        # iterate for the number of words in the trigger
        for line in lines:
            lineEntries = line.split(SPLIT_CHAR)
            lineTrigger = lineEntries[0]

            matchArgs = await self.botMatchString(trigger, lineTrigger)
            # add new response to trigger
            # if the trigger is matched, add it to the matches list
            if matchArgs[0]:
                matches.append((lineEntries, matchArgs[1]))  # save the chopped up line and the match probability

        print("Matches: ", matches)
        # if there are any matches, choose the one with the highest probability
        if len(matches) > 0:
            highestMatch = matches[0]
            for match in matches:
                # if line is higher probability than saved match, replace
                if match[1] > highestMatch[1]:
                    highestMatch = match

            # get random response from list
            responses = highestMatch[0][1:]
            response = random.choice(responses)
            return response

        return self.botNoResponse

    async def botMatchString(self, str1, str2):
        args = fuzzyMatchString(str1, str2, self.settings[ARGS.WEIGHTS], self.settings[ARGS.PROB_MIN])
        self.lastScores = args[2]
        if args[3] is not None: print(args[2])
        return args[0:2]


def sanitize_string(input):
    return re.sub(r'[^a-zA-Z ]', '', str(input).strip().lower())


# match strings with fuzzywuzzy
def fuzzyMatchString(str1, str2, weights, probMin):
    output = None
    partialRatio = fuzz.partial_ratio(str1, str2)
    tokenSetRatio = fuzz.token_set_ratio(str1, str2)
    tokenSortRatio = fuzz.token_sort_ratio(str1, str2)
    ratio = fuzz.ratio(str1, str2)
    # partialTokenSetRatio = fuzz.partial_token_set_ratio(str1, str2)
    # partialTokenSortRatio = fuzz.partial_token_sort_ratio(str1, str2)

    scores = [ratio, partialRatio, tokenSetRatio, tokenSortRatio]

    # weight scores as probabilities, sum them, and divide by number of scores
    sumScores = 0
    for i in range(len(scores)):
        sumScores += (scores[i] / 100) * weights[i]

    probability = sumScores / len(scores)

    isMatch = False
    if probability > probMin:
        isMatch = True

        output = "Analysis of \"", str(str1), "\" with \"", str(str2), "\" \n", \
                 "Matched? ", str(isMatch), "\n", \
                 "Partial ratio: ", str(partialRatio), "\n", \
                 "Ratio: ", str(ratio), "\n", \
                 "Token set ratio: ", str(tokenSetRatio), "\n", \
                 "Token sort ratio: ", str(tokenSortRatio), "\n", \
                 "Probability: ", str(probability)

    return isMatch, probability, scores, output  # return matching status and individual scores


def save_obj(obj, name):
    with open('obj/' + name + '.pkl', 'wb+') as f:
        pickle.dump(obj, f, pickle.DEFAULT_PROTOCOL)


def load_obj(name):
    with open('obj/' + name + '.pkl', 'rb') as f:
        return pickle.load(f)
