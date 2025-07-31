"""
Zephyr Include Map
v0.22
By Shao Ming (smwikipedia@163.com or smrtos@163.com)

This tool generates include map for a Zephyr RTOS C source file.
The generation is based on C preprocessor result.

Sample:
python3 GenIncludeMap2.py  -z ~/zephyr/ -b ~/zephyr/build -t ~/toolchain/arm32-none-eabi/bin/arm-none-eabi-gcc -s ~/zephyr/samples/drivers/uart/echo_bot/src/main.c

"""
import sys
import os.path
import re
import subprocess
import glob
import argparse
from graphviz import Digraph

def ErrorHandling(everything, errNo):
    if(errNo == 1):
        print("The source file [{0}] is not part of the build.".format(everything["srcFileFullPath"]))
    elif (errNo == 2):
        print("\"build.ninja\" file cannot be found at [{0}].".format(everything["bldDir"]))
        print("Did you specify a wrong build folder?")
    elif (errNo == 3):
        print("Failed to render the graph.")
        print("Is the file [{0}] writable?".format(everything["pdfFileFullPath"]))
    sys.exit(0)
    return

def GetNinjaBuildFile(everything):
    ninjaBldFileFullPath = os.path.join(everything["bldDir"], "build.ninja")
    if(not os.path.exists(ninjaBldFileFullPath)):
        ErrorHandling(everything, 2)
    everything["ninjaBldFile"] = ninjaBldFileFullPath    
    print(f"[Ninja build file found:]{os.linesep}{everything["ninjaBldFile"]}")
    return

def GetNinjaBuildBlock4SourceFile(everything):
    srcFileFullPath = everything["srcFileFullPath"]
    zephyrDir = everything["zephyrDir"]
    srcFileRelativePath = os.path.relpath(srcFileFullPath, zephyrDir).replace(os.path.sep, "/")
    target = r"build\s.*{0}".format(srcFileRelativePath)
    nextTarget = r"build\s[^:]*:"
    buildBlockLines = []
    with open(everything["ninjaBldFile"], "r") as f:
        lines = f.readlines()
        collect = False
        for line in lines:
            if(re.match(target, line)):
                collect = True
                continue
            if(collect and re.match(nextTarget, line)):
                break
            if(collect):
                buildBlockLines.append(line)
    if(len(buildBlockLines) == 0):
        ErrorHandling(everything, 1)
    everything["buildBlockLines"] = buildBlockLines
    return

def LoadIncludeSearchPaths(everything):
    includeSearchPaths = []
    for line in everything["buildBlockLines"]:
        if("INCLUDES" in line):
            break

    # -I<dir>
    m = re.findall(r"(-I[^\s]+)", line) #(-I[^\s]+)|(-isystem\s[^\s]+)
    includeSearchPaths.extend(x[2:] if not x[-1] == "." else x[2:-1] for x in m)
    rawIncludeSearchPaths = [x if os.path.isabs(x) else os.path.join(everything["bldDir"], x) for x in includeSearchPaths]
    includeSearchPaths = " ".join(["-I{0}".format(os.path.normpath(x)) for x in rawIncludeSearchPaths])

    # -isystem <dir>
    rawSystemSearchPaths = re.findall(r"(-isystem\s[^\s]+)", line)
    systemSearchPaths = " ".join(rawSystemSearchPaths)

    everything["includeSearchPaths"] = "{0} {1}".format(includeSearchPaths, systemSearchPaths)
    return

def LoadConfigMacros(everything):
    for line in everything["buildBlockLines"]:
        if("DEFINES" in line):
            break
    m = re.match(r".*=\s+(.*)", line)
    configMacros = m.group(1) #load DEFINES from the build.ninja
    everything["configMacros"] = configMacros
    return

def LoadBuildFlags(everything):
    bldFlags = list()
    for line in everything["buildBlockLines"]:
        if("FLAGS" in line):
            break
    m = re.match(r".*=\s+(.*)", line)
    bldFlags = m.group(1) #load FLAGS from the build.ninja
    everything["bldFlags"] = bldFlags
    return

def PreProcessSrcFile(everything):
    GetNinjaBuildFile(everything)
    GetNinjaBuildBlock4SourceFile(everything)
    LoadIncludeSearchPaths(everything)
    LoadConfigMacros(everything)
    LoadBuildFlags(everything)

    cmdString = r"{0} -E {1} {2} {3} {4}".format(everything["gccFullPath"], everything["configMacros"], everything["includeSearchPaths"], everything["bldFlags"], everything["srcFileFullPath"])
    srcFile = os.path.basename(everything["srcFileFullPath"])
    ppSrcFile = "pp." + srcFile
    ppSrcFileFullpath = os.path.join(".", ppSrcFile)
    everything["ppFileFullPath"] = ppSrcFileFullpath
    # print (f"preprocessed file: {ppSrcFileFullpath}")

    with open(ppSrcFileFullpath, "w") as f:
        subprocess.run(cmdString, stdout=f, shell=True)
    return

def GenerateGraphMatrix(everything):
    lineStack = []
    lineStack.append(os.path.normpath(os.path.realpath(everything["srcFileFullPath"])))
    gm = everything["graphMatrix"]

    with open(everything["ppFileFullPath"], "r") as f:
        fileContent = f.read()
    
    #https://gcc.gnu.org/onlinedocs/gcc-3.4.6/cpp/Preprocessor-Output.html
    lineMarkerRegex = r"#\s+\d+\s+\"(.*)\"\s+([12])"
    lineMarkers = re.findall(lineMarkerRegex, fileContent)
    for rawLineMarker in lineMarkers:
        filePath = os.path.normpath(os.path.realpath(rawLineMarker[0]))
        fileFlag = rawLineMarker[1]
        if(fileFlag == '1'):
            fromFile = lineStack[-1]
            lineStack.append(filePath)
            if(not fromFile in gm.keys()):
                gm[fromFile] = []
            toFile = filePath
            if(toFile not in gm[fromFile]):
                gm[fromFile].append(toFile)
        elif (fileFlag == '2'):
            lineStack.pop(-1) 
    return

def IsGeneratedFile(everything, filePath):
    # return os.path.relpath(filePath, everything["bldDir"]) in filePath
    return everything["bldDir"] in os.path.realpath(os.path.abspath(filePath))

def IsZephyrNativeFile(everything, filePath):
    # return os.path.relpath(filePath, everything["zephyrDir"]) in filePath
    return everything["zephyrDir"] in os.path.realpath(os.path.abspath(filePath))

def IsTheStartingNode(everything, filePath):
    return everything["srcFileFullPath"] in os.path.realpath(os.path.abspath(filePath))

def IsToolChainFile(everything, filePath):
    # return everything["gccIncludePath"] in os.path.realpath(os.path.abspath(filePath))
    return "zephyr-sdk" in os.path.realpath(os.path.abspath(filePath))

def DetermineNodeLooks(everything, node):
    nodeText = os.path.relpath(node, everything["zephyrDir"]).replace(os.path.sep, "/\n")
    shape = "oval"
    style = "filled"
    fontName = ""
    if(IsGeneratedFile(everything, node)):            
        nodeColor = "orange"
    elif(IsTheStartingNode(everything, node)):
        shape = "box"
        nodeColor = "green"
        fontName = "bold"
    # elif(IsToolChainFile(everything, node)):
    #     shape = "diamond"
    #     # nodeText = r"\<{0}\>".format(os.path.basename(node)) # use "<xxx>" for toolchain headers
    #     # print (f"\t{os.path.relpath(node, everything["gccIncludePath"])} - {node}")
    #     # nodeText = os.path.relpath(node, everything["gccIncludePath"]).replace(os.path.sep, "/\n")
    #     nodeColor = "lightgrey"
    elif(IsZephyrNativeFile(everything, node)):
        nodeColor = "lightblue"
    else:
        nodeColor = "black"
        style = ""
    return tuple([nodeText, nodeColor, shape, style, fontName])

def AddLegends(graph):
    nodeText = "Generated Files"
    shape = "oval"
    style = "filled"
    nodeColor = "orange"
    graph.node(nodeText, label = nodeText, color = nodeColor, shape = shape, style = style, fontname = "bold")

    # nodeText = "Toolchain Files"
    # shape = "diamond"
    # style = "filled"
    # nodeColor = "lightgrey"
    # graph.node(nodeText, label = nodeText, color = nodeColor, shape = shape, style = style, fontname = "bold")

    nodeText = "In-Zephyr Files"
    shape = "oval"
    style = "filled"
    nodeColor = "lightblue"
    graph.node(nodeText, label = nodeText, color = nodeColor, shape = shape, style = style, fontname = "bold")

    nodeText = "Out-of-Zephyr Files"
    shape = "oval"
    style = ""
    nodeColor = "black"
    graph.node(nodeText, label = nodeText, color = nodeColor, shape = shape, style = style, fontname = "bold")
    pass

def DumpGraph(everything):
    gm = everything["graphMatrix"]
    print (f"Dump graph")
    for fromNode in gm.keys():
        print (f"{fromNode}:\n\t{gm[fromNode]}")

def GenerateGraph(everything):
    graph = Digraph(engine="dot", comment="Include Map for {0}".format(everything["srcFileFullPath"]))
    gm = everything["graphMatrix"]
    drawnNodes = []
    for fromNode in gm.keys():
        looks1 = DetermineNodeLooks(everything, fromNode)
        if(looks1[0] not in drawnNodes):
            graph.node(looks1[0], label = looks1[0], color = looks1[1], shape = looks1[2], style = looks1[3], fontname = looks1[4])
            drawnNodes.append(looks1[0])
        for toNode in gm[fromNode]:
            looks2 = DetermineNodeLooks(everything, toNode)
            if(looks2[0] not in drawnNodes):
                graph.node(looks2[0], label = looks2[0], color = looks2[1], shape = looks2[2], style = looks2[3], fontname = looks2[4])
                drawnNodes.append(looks2[0])
            graph.edge(looks1[0], looks2[0])

    AddLegends(graph)

    graphFileName = os.path.basename(everything["srcFileFullPath"])
    try:
        pdfFileFullPath = os.path.realpath("./IncludeMap_{0}.gv.pdf".format(graphFileName))
        everything["pdfFileFullPath"] = pdfFileFullPath
        graph.render(os.path.realpath("./IncludeMap_{0}.gv".format(graphFileName)), view= False, format="pdf") # graphviz will add the pdf suffix
    except:
        print(sys.exc_info()[0])
        ErrorHandling(everything, 3)
    pass

def DoWork(everything):
    print(f"[Start generating include map for:]{os.linesep}{everything["srcFileFullPath"]}")
    PreProcessSrcFile(everything)
    GenerateGraphMatrix(everything)
    # DumpGraph(everything)
    GenerateGraph(everything)
    return

def ParseArgs():
    """
    Need to specify:
    - which artifacts to build
    - which overrides to apply
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-z", "--zephyrDir", required=True, type=str, help="the full path of the zephyr RTOS.")
    parser.add_argument("-b", "--bldDir", required=True, type=str, help="the Zephyr build folder where build.ninja file is located.")
    parser.add_argument("-t", "--gccFullPath", required=True, type=str, help="the full path of the GCC used to build Zephyr.")
    parser.add_argument("-s", "--srcFileFullPath", required=True, type=str, help="the full path of the Zephyr source file to generate include map for.")

    args = parser.parse_args()
    return args

def CleanseArgs(everything):
    # TODO...
    return

def OutputIncludeSearchPaths(everything):
    print("[The include search paths:]")
    for include in everything["includeSearchPaths"].split(" "):
        print(f"{include}", end="")
        if (not "isystem" in include):
            print()
        else:
            print(" ", end="")
    return

def CleanUp(everything):
    ppFileList = glob.glob("./pp.*")
    for ppFile in ppFileList:
        os.remove(ppFile)
    return

if __name__=="__main__":
    everything = dict()
    args = ParseArgs()
    everything["zephyrDir"] = os.path.realpath(os.path.abspath(os.path.normpath(args.zephyrDir)))
    everything["bldDir"] = os.path.realpath(os.path.abspath(os.path.normpath(args.bldDir)))
    everything["gccFullPath"] = os.path.realpath(os.path.abspath(os.path.normpath(args.gccFullPath)))
    everything["srcFileFullPath"] = os.path.realpath(os.path.abspath(os.path.normpath(args.srcFileFullPath)))
    everything["graphMatrix"] = dict() # <nodeA, [nodeX, nodeY, nodeZ, ...]>, A connects "to" X, Y, Z, ...
    CleanseArgs(everything)
    DoWork(everything)
    OutputIncludeSearchPaths(everything)
    CleanUp(everything)
    print (f"[Include map saved as:]{os.linesep}{everything["pdfFileFullPath"]}")
    sys.exit(0)
