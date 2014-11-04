#!/usr/bin/env python

import os
import sys

DESCRIPTION = """
Usage: {0} repositories* command [% command]*

Apply the command(s) to the listed set of repositories.
"""


def printUsageError(error):
    """
    Print the specified 'error', print the usage text, and exit with a failure 
    status.
    
    Args:
        error (string) : an error string to print.
    """
    print(error + "\n")
    print(DESCRIPTION).format(sys.argv[0]);
    sys.exit(-1)
    
def parseArgument(arguments, options, repositories, commands):
    """
    Parse the specified command line 'arguments' and populate the specified list of
    'repositories' and 'commands'.

    The 'arguments' string is expected to be in the form:
    
        arguments  ::= [options] <repository>+ <command>+ ('%' <command>)+        
        repository ::= string
        command    ::= string
        options    ::= '--' string
        
     Args:
        arguments (string) : the command line arguments to parse
        
        options ([string) : the parsed list of options
        
        repositories ([string]) : the parsed list of repositories
        
        commands ([[string]]) : the parsed list of commands, where each command 
          is a list of strings
    """

    class ParseState:
        options = 1
        repositories = 2
        commands = 3
        
    state    = ParseState.options
    command  = []
    
    for argument in arguments:
        if (state == ParseState.options):
            if ("--" == argument[0:2]):
                options.append(argument[2:])
            else:
                state = ParseState.repositories
         
                        
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
                
    if (len(commands) == 0):
        printUsageError("No commands specified.")
        
    if (len(repositories) == 0):
        
        printUsageError("No repositories specified.")

def main():
    repositories = []
    commands     = []
    options      = []
    
    parseArgument(sys.argv[1:], options, repositories, commands)
       
    print options
    print repositories
    print commands
    
if __name__ == "__main__":
    main()


