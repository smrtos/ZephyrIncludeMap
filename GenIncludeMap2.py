import sys
import os.path
import re
import io
import string
import json
import subprocess
import glob
from graphviz import Digraph

def GetNinjaBuildFile(everything):
    everything["ninjaBldFile"]= os.path.join(everything["bldDir"], "build.ninja")
    print("Ninja build file found:\n[%s]\n" % everything["ninjaBldFile"])
    return

def GetNinjaBuildBlock4SourceFile(everything):
    srcFileFullPath = everything["srcFileFullPath"]
    srcDir = everything["srcDir"]
    srcFileRelativePath = os.path.relpath(srcFileFullPath, srcDir).replace("\\", "/")
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
    return everything["bldDir"].lower() in filePath.lower()

def IsTheStartingNode(everything, filePath):
    return everything["srcFileFullPath"].lower() in filePath.lower()

def IsToolChainFile(everything, filePath):
    return everything["gccInstallDir"].lower() in filePath.lower()

def DetermineNodeLooks(everything, node):
    shape = "oval"
    style = "filled"
    fontName = ""
    if(IsGeneratedFile(everything, node)):            
        nodeText = os.path.relpath(node, everything["bldDir"]).replace("\\", "\n")
        nodeColor = "lightblue"
    elif(IsTheStartingNode(everything, node)):
        nodeText = os.path.relpath(node, everything["srcDir"]).replace("\\", "\n")
        shape = "box"
        nodeColor = "green"
        fontName = "bold"
    elif(IsToolChainFile(everything, node)):
        nodeText = os.path.relpath(node, everything["gccInstallDir"]).replace("\\", "\n")
        nodeColor = "lightgrey"        
    else:
        nodeText = os.path.relpath(node, everything["srcDir"]).replace("\\", "\n")
        nodeColor = "black"
        style = ""
    return tuple([nodeText, nodeColor, shape, style, fontName])

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
    graphFileName = os.path.basename(everything["srcFileFullPath"])
    graph.render("./IncludeMap_{0}.gv".format(graphFileName), view= False, format="pdf")
    pass

def DoWork(everything):
    print("Start generating include map for:\n[%s]\n" % everything["srcFileFullPath"])
    PreProcessSrcFile(everything)
    GenerateGraphMatrix(everything)
    GenerateGraph(everything)
    return

def Usage():
    print("\n")
    print("IncludeMap ver 0.1")
    print("By Shao, Ming (smwikipedia@163.com)")
    print("[Description]:")
    print("  This tool generates a map of included headers for a Zephyr .c file in the context of a Zephyr build.")
    print("[Pre-condition]:")
    print("  A Zephyr build must be made before using this tool because some build-generated files are needed.")
    print("[Usage]:")
    print("  GenIncludeMap <srcDir> <bldDir> <gccFullPath> <srcFileFullPath>")
    print("  <srcDir>: the Zephyr source code folder.")
    print("  <bldDir>: the Zephyr build folder where build.ninja file is located.")
    print("  <gccFullPath>: the full path of the GCC used to build Zephyr.")
    print("  <srcFileFullPath>: the full path Zephyr source file to generate include map for.")
    return

def CleanseArgs(everything):
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
        print("Zephyr Include Map Generator ver 0.1")
        print("By Shao, Ming (smwikipedia@163.com)")
        everything["srcDir"] = os.path.abspath(os.path.normpath(sys.argv[1]))
        everything["bldDir"] = os.path.abspath(os.path.normpath(sys.argv[2]))
        everything["gccFullPath"] = os.path.abspath(os.path.normpath(sys.argv[3]))
        everything["gccInstallDir"] = os.path.abspath(os.path.normpath(sys.argv[4]))
        everything["srcFileFullPath"] = os.path.abspath(os.path.normpath(sys.argv[5]))
        # <nodeA, <nodeX, nodeY, nodeZ, ...>>, A connects "to" X, Y, Z, ...
        everything["graphMatrix"] = dict()
        CleanseArgs(everything)
        DoWork(everything)
        OutputIncludeSearchPaths(everything)
        CleanUp(everything)
    sys.exit(0)