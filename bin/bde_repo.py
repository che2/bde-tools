#!/usr/bin/env python

import os
import sys
import subprocess
import optparse

USAGE = "Usage: %prog repositories* command [% command]*"

DESCRIPTION = """
Apply the command(s) to the listed set of repositories.
""".strip()

class PlainHelpFormatter(optparse.IndentedHelpFormatter): 
    def format_description(self, description):
        if description:
            return description + "\n"
        else:
            return ""
    
def parseArgument(arguments, repositories, commands):
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
        subprocess.check_call(command)
    os.chdir(originalPath)

def runCommands(repositories, commands):
    for repository in repositories:
        runCommand(repository, commands)
        
def main():
    repositories = []
    commands     = []
    
    parser = optparse.OptionParser(
                          description = DESCRIPTION,
                          formatter = PlainHelpFormatter())
                          
    parser.disable_interspersed_args()
    
    parser.add_option("-v",
                      "--verbose",
                      action="store_true",
                      dest="verbose",
                      default=False,
                      help="Print verbose output")

    (options, args) = parser.parse_args()                      
    
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



    