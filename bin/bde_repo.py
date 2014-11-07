#!/usr/bin/env python

import re
import os
import sys
import subprocess
import optparse
import json


USAGE = """
 Usage: %prog [options] [repository]* command [% command]  # run commands*
        %prog [options] set  @[tag] [directory]*           # set a @tag
        %prog [options] list @[tag]*                       # list a @tag
"""

DESCRIPTION = """
Run Commands
------------
    %prog [options] [repository]* command [% command]

This will run a series of commands in a set of directories (typically git
repositories).  A 'repository' may either be a directory location, or a tag
(like @bde) which refers to a sequence of directory locations.  Multiple
commands can be seperated by '%'.  For example:

    %prog @bde ~/bde-bb git pull % waf configure build install

Will execute 'git pull', and then 'waf configure build install', in the
sequence of directories associated with '@bde' and then '~/bde-bb'.

Set Tag
-------
    %prog [options] set @[tag] [directory]*

This will associate the @tag with the listed directories.  For example

    %prog set @bde ~/bde-oss ~/bde-core

Will associate '@bde' with the directories '~/bde-oss/' '~/bde-core'.  This
configuration is persisted in a JSON configuration file ($HOME/.bde_repo.cfg,
by default)

List Tags
---------
    %prog [options] list (@[tag])*

This will list the directories associated with the (optionally) listed tags.
If no tags are supplied, all the tags are listed.  For example:

    %prog list @bde

Will list the directories associated with @bde. This information is retrieved
from a JSON configuration ($HOME/.bde_repo.cfg, by default).

Usage Example
-------------
    $ bde_gitcheckout.py https://github.com/bde.git gitserve:bde/bde-extra
               # checkout a couple git repositories (see bde_gitcheckout.py)
    $ bde_repo.py set @bde $pwd/bde $pwd/bde-extra
    $ bde_repo.py list @bde
    
     @bde '/my/home/dir/bde' '/my/home/dir/bde-extra'

    $ bde_repo.py @bde git checkout releases/2.22 % waf configure build install

Inspired by
-----------
  * http://mixu.net/gr/
""".strip()

DEFAULT_CONFIG_FILENAME = os.environ["HOME"] + "/.bde_repo_tags.cfg"

class PlainHelpFormatter(optparse.IndentedHelpFormatter):
    """
    Formatter that works with 'optparse' that does not modify the formatting
    of the text.
    """   
    def format_description(self, description):
        if description:
            return description + "\n"
        else:
            return ""


class InputError(Exception):
    """
    Exception raised for errors in the user input.

    Attributes:
        msg  -- explanation of the error
    """
    def __init__(self, msg):        
        self.msg = msg       


def isValidTag(tag):
    """
    Return 'true' if the specified 'tag' is a valid tag (a character
    string that starts with @).

    Tags must start with @, and may contain alpha-numeric characters, and
    '-', '_'.

    Parameters:
        tag (string) : the tag name to validate
    """
    return re.search("^@[a-zA-Z0-9\-_]*$", tag) is not None


def readTagsFromFile(filename):
    """
    Load the mapping of tags from the specified 'filename' and return the
    resulting dictionary.

    Parameters:
        filename (string) : the file from which to load the dictionary of tags

    Returns:
        dictionary : loaded tag dictionary
    """
    return json.load(open(filename,"r"))


def writeTagsToFile(filename, tags):
    """
    Write the specified dictionary of 'tags' to a file having the specified
    'filename'. 

    Parameters:
        filename (string) : the file to which to write the dictionary of tags

        tags (dictionary(string, list(string))) : the tags to write to the file
    """
    json.dump(tags, open(filename, "w"), indent = 2, sort_keys=True)


def parseDirectoryList(arguments):
    """
    Parse the specified 'arguments' and return the file system directories at
    the beginning of the argument list, and as well as the unparsed arguments.
    The argument list is expected to begin with a sequence of directories,
    i.e.:
        [directory]* [remaining argument]*

    E.g.:
       [ '~/', '@bde', 'remaining', 'arguments', 'at', 'the', 'end' ] 

    Parameters:
        tags (dictionary(string, list(string))) : a dictionary mapping tag
          names to directory locations.

        arguments (list(string)) : a list of command line arguments

    Returns:
        tuple(repositories, remainingArgs) : return the list of repository
           locations and the remaining unparsed arguments
    """       

    directories        = []
    remainingArguments = []

    for idx, arg in enumerate(arguments):
        if (os.path.isdir(arg)):
            directories.append(arg)
        else:
            remainingArguments = arguments[idx:]
            break

    return (directories, remainingArguments)

def parseRepositoryReferences(tags, arguments):
    """
    Parse the specified 'arguments' and return the directories of the
    repositories referred to at the beginning of the argument list, and as
    well as the unparsed arguments.  The argument list is expected to begin
    with a sequence of directories or tags (which refer to a list of
    directories), i.e.:
        [directory|@tag]* [remaining argument]*

    E.g.:
       [ '~/', '@bde', 'remaining', 'arguments', 'at', 'the', 'end' ] 

    Parameters:
        tags (dictionary(string, list(string))) : a dictionary mapping tag
          names to directory locations.

        arguments (list(string)) : a list of command line arguments

    Returns:
        tuple(repositories, remainingArgs) : return the list of repository
           locations and the remaining unparsed arguments
    """       
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
    """
    Parse the specified 'arguments' and return a sequence of commands.  The
    argument list is treated as a sequence of '%' separated shell commands,
    i.e.:
        ([command argument]* %)*

    E.g.:
        ['git', 'pull', '%', 'waf', 'configure', 'build', 'install']
    Parameters:
        arguments (list(string)) : a list of command line arguments

    Returns:
        list(list(strings)) : a list of shell commands, where each shell
          command is a list of arguments        
    """
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

def runCommand(options, directory, commands):
    """
    Run the specified list of 'commands' in the specified 'directory' using
    the specified 'options'.

    Parameters:
        options (optparse.Values) : configuration options
        
        directory (string) : directory in which to run the commands

        commands (string) : commands to run        
        
    """
    originalPath = os.getcwd()

    for command in commands:
        os.chdir(directory)
        
        if (options.verbose):
            print("\n> {0}$ {1}\n".format(directory,' '.join(command)))
            
        if (sys.platform == "win32"):
            # For a windows python, execute commands in a subshell (needed for
            # cleaner git bash integration)

            subprocess.check_call(' '.join(command), shell=True)
        else:
            subprocess.check_call(command)
    os.chdir(originalPath)

def runCommands(options, directories, commands):
    """
    Run the specified list of 'commands' in the specified list of
    'directories' using the specified 'options'.

    Parameters:
        options (optparse.Values) : configuration options
        
        directories (list(string)) : directories in which to run the commands

        commands (string) : commands to run
    """
    for repository in repositories:
        runCommand(options, repository, commands)


def processRunCommandsAction(tags, options, arguments):
    """
    Process the 'run-commands' action on the specified list of command-line
    'arguments', using the specified dictionary of 'tags' and command-line
    'options'

    Parameters:
        tags (dictionary(string, list(string))) : a dictionary mapping tag
          names to directory locations.

        options (optparse.Values) : configuration options
        
        arguments (list(string)) : command line arguments
    """
    (repositories, remainingArguments) = parseRepositoryReferences(tags,
                                                                   arguments)
    commands = parseCommands(remainingArguments)
    
    if (len(commands) == 0):
        raise InputError("No commands specified.")

    if (len(repositories) == 0):
        raise InputError("No repositories specified.")
     
    runCommands(options, repositories, commands)

	
    
def processSetTagAction(tags, options, arguments):
    """
    Process the 'set-tags' action on the specified list of command-line
    'arguments', using the specified dictionary of 'tags' and command-line
    'options'

    Parameters:
        tags (dictionary(string, list(string))) : a dictionary mapping tag
          names to directory locations.

        options (optparse.Values) : configuration options
        
        arguments (list(string)) : command line arguments
    """

    (directories, remainingArguments) = parseDirectoryList(arguments[1:])

    if (0 != len(remainingArguments)):
        raise InputError("Unexpected non-directory arguments: " + 
                     " ".join(remainingArguments))

    if (not isValidTag(arguments[0])):
        raise InputError("Invalid tag: " + args[0])

    tag = arguments[0]

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

def processListTagsAction(tags, options, args):
    """
    Process the 'list-tags' action on the specified list of command-line
    'arguments', using the specified dictionary of 'tags' and command-line
    'options'

    Parameters:
        tags (dictionary(string, list(string))) : a dictionary mapping tag
          names to directory locations.

        options (optparse.Values) : configuration options
        
        arguments (list(string)) : command line arguments
    """

    if (0 == len(args)):
        keys = sorted(tags.keys())
    else:
        keys = args
    
    for key in keys:
        if (not tags.has_key(key)):
            raise InputError("Invalid tag: {0}".format(key))
        print("{0} {1}".format(
            key, ' '.join(map(lambda x: "'" + x + "'", tags[key]))))

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

    parser.add_option(
        "-c",
        "--config",
        action="store",
        dest="configFileName",
        default=DEFAULT_CONFIG_FILENAME,
        help=
        "Configuration file name (default: $HOME/.bde_repo.cfg)".format(
                                                      DEFAULT_CONFIG_FILENAME))


    (options, args) = parser.parse_args()

    # Load the tags from the configuration file, if the file exists.
    tags = {}               
    if (os.path.isfile(options.configFileName)):
        if (options.verbose):
            print("Reading configuration file: {0}".format(
                                                       options.configFileName))
        tags = readTagsFromFile(options.configFileName)        
    elif (options.verbose):
        print("Configuration file not found: {0}".format(
                                                       options.configFileName))

    try:

        if (args[0] == "set"):
            tags = processSetTagAction(tags, options, args[1:])
            writeTagsToFile(options.configFileName, tags)
            if (options.verbose):
                print("Tags: {0}".format(tags))                

        elif (args[0] == "list"):
            processListTagsAction(tags, options, args[1:])

        else:
            processRunCommandsAction(tags, options, args)
            
    except InputError as e:
        parser.error(e.msg)
        
if __name__ == "__main__":
    main()

