from typing import List

import nodes
import programState
import programStateProxy
import asmParser
import lexer
import tokens
from high_order import foldR1
import visualizer
import visualizeProxy


# generateStacktraceElement:: ProgramState -> int -> String -> [String] -> String
# Generates a stacktrace element from an instruction address
def generateStacktraceElement(state: programState.ProgramState, address: int, fileName: str, lines: List[str]) -> str:
    instr: nodes.InstructionNode = programStateProxy.getInstructionFromMem(state, address)
    if isinstance(instr, nodes.SystemCall):
        return f"\tInternal function: {instr.name}"
    return f"\tFile \"{fileName}\", line {instr.line}:\n\t\t{lines[instr.line-1].strip()}"


# generateStacktrace:: ProgramState -> RunError -> String -> [String] -> String
# Generates the stacktrace of an error
def generateStacktrace(state: programState.ProgramState, error: programState.RunError, fileName: str, lines: List[str]) -> str:
    # Get return addresses from the stack
    sp: int = programStateProxy.getReg(state, "SP")
    stackSize = programStateProxy.getLabelAddress(state, "__STACKSIZE")
    stack: List[nodes.Node] = state.memory[sp >> 2:stackSize >> 2]
    callbacks = list(map(lambda n: generateStacktraceElement(state, n.value, fileName, lines), filter(lambda x: isinstance(x, nodes.DataNode) and x.source == "LR", stack) ) )

    # Generate the error
    res = f"\033[31m"  # Red color
    res += "Traceback (most recent call first):\n"
    res += generateStacktraceElement(state, programStateProxy.getReg(state, "PC"), fileName, lines) + '\n'
    if not state.hasReturned:
        res += generateStacktraceElement(state, programStateProxy.getReg(state, "LR"), fileName, lines) + '\n'
    res += foldR1(lambda a, b: a + "\n" + b, callbacks) + '\n'
    res += error.message + '\n'
    return res + f"\033[0m"  # Normal color


# runProgram:: ProgramState -> (ProgramState -> RunError -> String) -> ProgramState
def runProgram(state: programState.ProgramState, fileName: str, lines: List[str]) -> programState.ProgramState:
    node: nodes.InstructionNode = programStateProxy.getInstructionFromMem(state, programStateProxy.getReg(state, "PC"))
    if isinstance(node, nodes.InstructionNode):
        # Execute the instruction
        state, err = visualizeProxy.runLogger(node, lines)(state)
        # Exception handling
        if err is not None:
            if isinstance(err, programState.RunError):
                if err.errorType == programState.RunError.ErrorType.Error:
                    print(generateStacktrace(state, err, fileName, lines))
                    return state
                elif err.errorType == programState.RunError.ErrorType.Warning:
                    print(generateStacktrace(state, err, fileName, lines))
                    pass
            if isinstance(err, programState.StopProgram):
                return state
        # Set a flag in the ProgramState when a subroutine returned. This way the stacktrace generator knows to not print a stacktrace element for the link register
        pc = programStateProxy.getReg(state, "PC")
        if pc == programStateProxy.getReg(state, "LR"):
            state.hasReturned = True
        # increment the program counter
        state = programStateProxy.setReg(state, "PC", pc + 4)
    return runProgram(state, fileName, lines)


# parseAndRun:: String -> int -> String -> ProgramState
# calls the parser and the lexer and runs the parsed program
def parseAndRun(fileName: str, stackSize: int, startLabel: str, useGUI: bool) -> programState.ProgramState:
    file = open(fileName, "r")
    lines = file.readlines()

    file_contents: str = foldR1(lambda X, Y: X + Y, lines)

    loadedTokens = lexer.lexFile(file_contents)
    loadedTokens: List[tokens.Token] = lexer.fixMismatches(loadedTokens, file_contents)

    if lexer.printErrors(loadedTokens, fileName):
        exit(-1)

    context = asmParser.parse(loadedTokens)
    errCount = asmParser.printErrors(context, fileName)
    if errCount > 0:
        exit(-1)

    state = programStateProxy.generateProgramState(context, stackSize, startLabel, fileName, useGUI)

    if useGUI:
        visualizeProxy.initRegs(state.registers)

    res = runProgram(state, fileName, lines)
    if useGUI:
        # Disable the GUI when the program is finished
        visualizer.nextButton.configure(state="disabled")
        visualizer.readButton.configure(state="disabled")
        visualizer.writeButton.configure(state="disabled")

    return res