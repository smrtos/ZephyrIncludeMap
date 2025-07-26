import sys
import os.path
import re
import subprocess
import glob
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
    print("Ninja build file found:\n[%s]\n" % everything["ninjaBldFile"])
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
    m = re.findall(r"(-I[^\s]+)", line) #(-I[^\s]+)|(-isystem\s[^\s]+)
    includeSearchPaths.extend(x[2:] if not x[-1] == "." else x[2:-1] for x in m)
    rawIncludeSearchPaths = [x if os.path.isabs(x) else os.path.join(everything["bldDir"], x) for x in includeSearchPaths]
    includeSearchPaths = " ".join(["-I{0}".format(os.path.normpath(x)) for x in rawIncludeSearchPaths])

    rawSystemSearchPaths = re.findall(r"(-isystem\s[^\s]+)", line)
    systemSearchPaths = " ".join(rawSystemSearchPaths)

    toolchainSearchPath = " {0}{1}".format("-I", everything["gccIncludePath"])
    includeSearchPaths += toolchainSearchPath

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
    print (f"preprocessed file: {ppSrcFileFullpath}")

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
    return everything["bldDir"].lower() in filePath.lower()

def IsZephyrNativeFile(everything, filePath):
    # return os.path.relpath(filePath, everything["zephyrDir"]) in filePath
    return everything["zephyrDir"].lower() in filePath.lower()

def IsTheStartingNode(everything, filePath):
    return everything["srcFileFullPath"].lower() in filePath.lower()

def IsToolChainFile(everything, filePath):
    return everything["gccIncludePath"].lower() in filePath.lower()

def DetermineNodeLooks(everything, node):
    shape = "oval"
    style = "filled"
    fontName = ""
    if(IsGeneratedFile(everything, node)):            
        nodeText = os.path.relpath(node, everything["bldDir"]).replace(os.path.sep, "/\n")
        nodeColor = "orange"
    elif(IsTheStartingNode(everything, node)):
        nodeText = os.path.relpath(node, everything["zephyrDir"]).replace(os.path.sep, "/\n")
        shape = "box"
        nodeColor = "green"
        fontName = "bold"
    elif(IsToolChainFile(everything, node)):
        shape = "diamond"
        # nodeText = r"\<{0}\>".format(os.path.basename(node)) # use "<xxx>" for toolchain headers
        # print (f"\t{os.path.relpath(node, everything["gccIncludePath"])} - {node}")
        nodeText = os.path.relpath(node, everything["gccIncludePath"]).replace(os.path.sep, "/\n")
        nodeColor = "lightgrey"
    elif(IsZephyrNativeFile(everything, node)):
        nodeText = os.path.relpath(node, everything["zephyrDir"]).replace(os.path.sep, "/\n")
        nodeColor = "lightblue"
    else:
        nodeText = os.path.relpath(node, everything["zephyrDir"]).replace(os.path.sep, "/\n")
        nodeColor = "black"
        style = ""
    return tuple([nodeText, nodeColor, shape, style, fontName])

def AddLegends(graph):
    nodeText = "Generated Files"
    shape = "oval"
    style = "filled"
    nodeColor = "orange"
    graph.node(nodeText, label = nodeText, color = nodeColor, shape = shape, style = style, fontname = "bold")

    nodeText = "Toolchain Files"
    shape = "diamond"
    style = "filled"
    nodeColor = "lightgrey"
    graph.node(nodeText, label = nodeText, color = nodeColor, shape = shape, style = style, fontname = "bold")

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
    print("Start generating include map for:\n[%s]\n" % everything["srcFileFullPath"])
    PreProcessSrcFile(everything)
    GenerateGraphMatrix(everything)
    # DumpGraph(everything)
    GenerateGraph(everything)
    return

def Usage():
    print("\n")
    print("IncludeMap ver 0.2")
    print("By Shao Ming (smwikipedia@163.com or smrtos@163.com)")
    print("[Description]:")
    print("  This tool generates a map of included headers for a Zephyr .c file in the context of a Zephyr build.")
    print("[Pre-condition]:")
    print("  A Zephyr build must be made before using this tool because some build-generated files are needed.")
    print("[Usage]:")
    print("  GenIncludeMap <zephyrDir> <bldDir> <gccFullPath> <srcFileFullPath>")
    print("  <zephyrDir>: the Zephyr folder path.")
    print("  <bldDir>: the Zephyr build folder where build.ninja file is located.")
    print("  <gccFullPath>: the full path of the GCC used to build Zephyr.")
    print("  <gccIncludePath>: the full path of the include directory that comes with your GCC bundle.")
    print("  <srcFileFullPath>: the full path of the Zephyr source file to generate include map for.")
    return

def CleanseArgs(everything):
    # TODO...
    return

def OutputIncludeSearchPaths(everything):
    print("The include search paths:")
    for include in everything["includeSearchPaths"].split(" "):
        print(os.path.normpath(include))
    return

def CleanUp(everything):
    ppFileList = glob.glob("./pp.*")
    for ppFile in ppFileList:
        os.remove(ppFile)
    return

if __name__=="__main__":
    everything = dict()    
    if(len(sys.argv)!= 6):
        Usage()
    else:
        print("Zephyr Include Map Generator ver 0.2")
        print("By Shao Ming (smwikipedia@163.com or smrtos@163.com)")
        everything["zephyrDir"] = os.path.realpath(os.path.abspath(os.path.normpath(sys.argv[1])))
        everything["bldDir"] = os.path.realpath(os.path.abspath(os.path.normpath(sys.argv[2])))
        everything["gccFullPath"] = os.path.realpath(os.path.abspath(os.path.normpath(sys.argv[3])))
        everything["gccIncludePath"] = os.path.realpath(os.path.abspath(os.path.normpath(sys.argv[4])))
        everything["srcFileFullPath"] = os.path.realpath(os.path.abspath(os.path.normpath(sys.argv[5])))
        everything["graphMatrix"] = dict() # <nodeA, [nodeX, nodeY, nodeZ, ...]>, A connects "to" X, Y, Z, ...
        CleanseArgs(everything)
        DoWork(everything)
        OutputIncludeSearchPaths(everything)
        CleanUp(everything)
    sys.exit(0)
