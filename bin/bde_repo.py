#!/usr/bin/env python

import os
import sys
import subprocess
import optparse
import pickle


# =============   Options Parsing =================

USAGE = """
   Usage: %prog [options] [repository]* command [% command]*
          %prog [options] set  @[tag] [repository]*
          %prog [options] list @[tag]*
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


class InputError(Exception):
    """Exception raised for errors in the input.

    Attributes:
        msg  -- explanation of the error
    """
    def __init__(self, msg):        
        self.msg = msg       

def runCommand(options, repository, commands):
    originalPath = os.getcwd()

    for command in commands:
        os.chdir(repository)
        
        if (options.verbose):
            print("\n> {0}$ {1}\n".format(repository,' '.join(command)))
            
        if (sys.platform == "win32"):
            # For a windows python, execute commands in a subshell (needed for
            # cleaner git bash integration)

            subprocess.check_call(' '.join(command), shell=True)
        else:
            subprocess.check_call(command)
    os.chdir(originalPath)

def runCommands(options, repositories, commands):
    for repository in repositories:
        runCommand(options, repository, commands)

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

def parseRepositories(tags, arguments):
    repositories       = []
    remainingArguments = []

    for idx, arg in enumerate(arguments):
        if (arg[0] == "@"):
            if (not tags.has_key(arg)):
                raise InputError("Invalid tag: {0}".format(arg))
            repositories = repositories + tags[arg]
        elif (os.path.isdir(arg)):
            repositories.append(arg)
        else:
            remainingArguments = arguments[idx:]
            break
            
    return (repositories, remainingArguments)

def parseCommands(arguments):
    commands = []
    command  = []
    
    for argument in arguments:
        if (argument != "%"):
            command.append(argument)
        else:
            commands.append(command)
            command = []

    if (len(command) != 0):
        commands.append(command)
    return commands

def processRunCommands(tags, options, arguments):
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
    (repositories, remainingArguments) = parseRepositories(tags, arguments)
    commands = parseCommands(remainingArguments)
    
    if (len(commands) == 0):
        raise InputError("No commands specified.")

    if (len(repositories) == 0):
        raise InputError("No repositories specified.")
     
    runCommands(options, repositories, commands)
	
def isValidTag(tag):
    #TBD: Improve this
    return 1 < len(tag) and "@"==tag[0]

def readTagsFromFile(filename):
    #TBD: Improve this
    return pickle.load(open(filename,"rb"))

def writeTagsToFile(filename, tags):
    #TBD: Improve this
    pickle.dump(tags, open(filename, "wb"))
    
def processSetTag(tags, options, args):
    (directories, remainingArguments) = processDirectoryArguments(args[1:])

    if (0 != len(remainingArguments)):
        raise InputError("Unexpected non-directory arguments: " + 
                     " ".join(remainingArguments))

    if (not isValidTag(args[0])):
        raise InputError("Invalid tag: " + args[0])

    tag = args[0]

    if (0 < len(directories)):
        if (options.verbose):
            print("{0} = {1}".format(tag, directories))
        tags[tag] = directories
    else:
        if (options.verbose):
            print("remove {0}".format(tag, directories))
        if (tags.has_key(tag)):
            del tags[tag]
    
    return tags

def processListTags(tags, options, args):
    if (0 == len(args)):
        keys = sorted(tags.keys())
    else:
        keys = args
    
    for key in keys:
        if (not tags.has_key(key)):
            raise InputError("Invalid tag: {0}".format(key))
        print("{0} {1}".format(key, ' '.join(map(lambda x: "'" + x + "'", tags[key]))))

def main():
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


    (options, args) = parser.parse_args()
       
    tags = {}    
           
    if (os.path.isfile(options.configFileName)):
        if (options.verbose):
            print("Reading configuration file: {0}".format(options.configFileName))
        tags = readTagsFromFile(options.configFileName)    
    elif (options.verbose):
        print("Configuration file not found: {0}".format(options.configFileName))

    try:
        if (args[0] == "set"):
            tags = processSetTag(tags, options, args[1:])
            writeTagsToFile(options.configFileName, tags)
            if (options.verbose):
                print("Tags: {0}".format(tags))
        elif (args[0] == "list"):
            processListTags(tags, options, args[1:])
        else:
            processRunCommands(tags, options, args)
            
    except InputError as e:
        parser.error(e.msg)
        
if __name__ == "__main__":
    main()

