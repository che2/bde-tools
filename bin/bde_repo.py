#!/usr/bin/env python

import os
import sys
import sets
import subprocess
import optparse
import pickle


# =============   Options Parsing =================

USAGE = """
   Usage: %prog [options] repositories* command [% command]*
          %prog [options] (+|-)@tag repositories*
"""

DESCRIPTION = """
Apply the command(s) to the listed set of repositories.
""".strip()

DEFAULT_CONFIG_FILENAME = os.environ["HOME"] + "/.bde_repo.cfg"

class PlainHelpFormatter(optparse.IndentedHelpFormatter):
    def format_description(self, description):
        if description:
            return description + "\n"
        else:
            return ""

# =========  Tag Dictionary =========


def parseArgument(arguments, repositories, commands):
    """
    Parse the specified command line 'arguments' and populate the specified list
    of 'repositories' and 'commands'.

    The 'arguments' string is expected to be in the form:

        arguments  ::= [options] <repository>+ <command>+ ('%' <command>)+
        repository ::= string
        command    ::= string
        options    ::= '--' string

     Args:
        arguments (string) : the command line arguments to parse

        repositories ([string]) : the parsed list of repositories

        commands ([[string]]) : the parsed list of commands, where each command
          is a list of strings
    """

    class ParseState:
        repositories = 1
        commands = 2

    state    = ParseState.repositories
    command  = []

    for argument in arguments:
        if (state == ParseState.repositories):
            if (os.path.isdir(argument)):
                repositories.append(argument)
            else:
                state = ParseState.commands

        if (state == ParseState.commands):
            if (argument != "%"):
                command.append(argument)
            else:
                commands.append(command)
                command = []

    if (len(command) != 0):
        commands.append(command)

def runCommand(repository, commands):
    originalPath = os.getcwd()

    for command in commands:
        os.chdir(repository)

        if (sys.platform == "win32"):
            # For a windows python, execute commands in a subshell (needed for
            # cleaner git bash integration)

            subprocess.check_call(' '.join(command), shell=True)
        else:
            subprocess.check_call(command)
    os.chdir(originalPath)

def runCommands(repositories, commands):
    for repository in repositories:
        runCommand(repository, commands)

def extractOptions(argv):
    options   = []
    arguments = []

    for idx, arg in enumerate(argv):
        if (arg[0] == "-" and arg[1]!="@"):
            options.append(arg)
        else:
            arguments = argv[idx:]
            break

    return (options, arguments)


def processDirectoryArguments(arguments):
    directories        = []
    remainingArguments = []

    for idx, arg in enumerate(arguments):
        if (os.path.isdir(arg)):
            directories.append(arg)
        else:
            remainingArguments = arguments[idx:]
            break

    return (directories, remainingArguments)

def isValidTag(tag):
    #TBD: Improve this
    return 1 < len(tag)

def readTagsFromFile(filename):
    #TBD: Improve this
    return pickle.load(open(filename,"rb"))

def writeTagsToFile(filename, tags):
    #TBD: Improve this
    pickle.dump(tags, open(filename, "wb"))
    
def processTagChange(tags, options, args):
    (directories, remainingArguments) = processDirectoryArguments(args[1:])

    if (0 != len(remainingArguments)):
        parser.error("Unexpected non-directory arguments: " + 
                     " ".join(remainingArguments))

    if (not isValidTag(args[0][1:])):
        parser.error("Invalid tag: " + args[0])

    tag = args[0][1:]
    add = args[0][0] == "+"

    if (tags.has_key(tag)):
        adjustedDirectories = tags[tag]
    else:
        adjustedDirectories = sets.Set()

    if (add):
        if (options.verbose):
            print("{0} add {1}".format(tag, directories))
        adjustedDirectories.update(directories)
    else:
        if (options.verbose):
            print("{0} remove {1}".format(tag, directories))
        adjustedDirectories.difference(directories)

    tags[tag] = adjustedDirectories
    return tags


def main():

    # The tag removal command, -@tag, will be treated as an options
    # by optparse, so we extract the actual options.
    (options, args) = extractOptions(sys.argv[1:])


    parser = optparse.OptionParser(
                        usage = USAGE,
                        description = DESCRIPTION,
                        formatter   = PlainHelpFormatter())

    parser.disable_interspersed_args()

    parser.add_option("-v",
                      "--verbose",
                      action="store_true",
                      dest="verbose",
                      default=False,
                      help="Print verbose output")

    parser.add_option("-c",
                      "--config",
                      action="store",
                      dest="configFileName",
                      default=DEFAULT_CONFIG_FILENAME,
                      help="Configuration file name (default: {0})".format(
                          DEFAULT_CONFIG_FILENAME))


    (options, dummy) = parser.parse_args(options)
       
    if (0 == len(args)):
        parser.error("No repositories or commands supplied.")

    tags = {}    
    if (os.path.isfile(options.configFileName)):
        tags = readTagsFromFile(options.configFileName)    

    if (args[0][0:2] == "-@" or args[0][0:2] == "+@"):
        tags = processTagChange(tags, options, args)
        print tags
        writeTagsToFile(options.configFileName, tags)

    else:
        print("Not tag?")
#       processAction(options, args)

def junk():
    repositories = []
    commands     = []
    parseArgument(args, repositories, commands)

    if (len(commands) == 0):
        parser.error("No commands specified.")

    if (len(repositories) == 0):
        parser.error("No repositories specified.")

    if (options.verbose):
        print options
        print repositories
        print commands

	
    runCommands(repositories, commands)

if __name__ == "__main__":
    main()

