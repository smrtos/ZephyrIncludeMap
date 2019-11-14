import sys
import os.path
import re
import io
import string
import json
import subprocess
import glob
from graphviz import Digraph

def GetAutoConfHeader(everything):
    everything["autoConfHeader"]=os.path.join(everything["bldDir"], "zephyr", "include", "generated", "autoconf.h")
    print("autoconf.h header found:\n[%s]\n" % everything["autoConfHeader"])
    return

def GetNinjaBuildFile(everything):
    everything["ninjaBldFile"]= os.path.join(everything["bldDir"], "build.ninja")
    print("Ninja build file found:\n[%s]\n" % everything["ninjaBldFile"])
    return

def AddCompilerIdMacro(everything):
    # for now, only consider __GNUC__
    everything["configMacros"].append("-D__GNUC__")
    return

def LoadConfigMacros(everything):
    configMacros = list()
    with open(everything["ninjaBldFile"], "r") as f:
        lines = f.readlines()
        for line in lines:
            if("DEFINES" in line):
                break #all the DEFINES in build.ninja are the same, so picking one is enough.
    m = re.findall(r"(-D[^\s=]+(=[^\s]+)?)+", line) #\s*-D([^\s=]+)
    configMacros.extend(x[0] for x in m) #load DEFINES from the build.ninja

    GetAutoConfHeader(everything)
    with open(everything["autoConfHeader"], "r") as f: #load #defines from the autoconf.h
        lines = f.readlines()
        for line in lines:
            m = re.match(r"#define\s+([^\s]+)\s+([^\s]+)", line)
            if(not m is None):
                if(len(m.groups()) == 2): #macro with value
                    configMacros.append("-D{0}={1}".format(m.group(1), m.group(2)))
                elif(len(m.groups()) == 1): # macro with no value
                    configMacros.append("-D{0}".format(m.group(1)))
    everything["configMacros"] = configMacros
    AddCompilerIdMacro(everything)
    return

def LoadIncludeSearchPaths(everything):
    includeSearchPaths = list()
    with open(everything["ninjaBldFile"], "r") as f:
        lines = f.readlines()
        for line in lines:
            if("INCLUDES" in line):
                break #all the INCLUDES in build.ninja are the same, so picking one is enough.
    m = re.findall(r"(-I[^\s]+)+", line) #\s*-D([^\s=]+)
    includeSearchPaths.extend(x[2:] if not x[-1] == "." else x[2:-1] for x in m)
    rawIncludeSearchPaths = [x if os.path.isabs(x) else os.path.join(everything["bldDir"], x) for x in includeSearchPaths]
    everything["includeSearchPaths"] = [os.path.normpath(x) for x in rawIncludeSearchPaths]
    return

def PreProcessSrcFile(everything, srcFileFullpath):
    cmdString = r"pcpp --passthru-unfound-includes <MACROS> <INPUT_SRC>"
    allMacros = " ".join(everything["configMacros"])
    srcFile = os.path.basename(srcFileFullpath)
    #srcFolder = os.path.dirname(srcFileFullpath)
    ppSrcFile = "pp." + srcFile
    ppSrcFileFullpath = os.path.join(".", ppSrcFile)
    itemTuple = tuple([srcFileFullpath, ppSrcFileFullpath])
    backlog = everything["backlog"]
    if(not itemTuple in backlog.keys()):
        cmdString = cmdString.replace(r"<MACROS>", allMacros)
        cmdString = cmdString.replace(r"<INPUT_SRC>", srcFileFullpath)
        with open(ppSrcFileFullpath, "w") as f:
            subprocess.run(cmdString, stdout=f, shell=True)
    # each time a file is pre-processed, it should be placed into the backlog for later include map generation.
    # all the pp.* files wil be saved in the working directory and will be deleted after the include map is generated.
    # this function focus on pre-processing, no backlog logic should be placed here.
    return itemTuple

def AddItemToBacklog(everything, srcFileFullpath):
    if(os.path.isabs(srcFileFullpath)): # skip preprocessing for the header provided by the compiler
        itemTuple = PreProcessSrcFile(everything, srcFileFullpath)
        if(not itemTuple in everything["backlog"].keys()):
            everything["backlog"][itemTuple] = False # boolean value indicates whether this file has been included in the map 
    else:
        srcFileRelativePath = srcFileFullpath # just for readability
        itemTuple = tuple([srcFileRelativePath, "not-resolved-header"])
        everything["backlog"][itemTuple] = False
    return

def GetNextItemFromBacklog(everything):
    backlog = everything["backlog"]
    for t in backlog.keys():
        if(not backlog[t] ): # <srcFileFullpath, preprocessedSrcFile> handled or not
            return t # <srcFileFullpath, preprocessedSrcFile>
    return None

def ResolveFullPathForHeader(everything, header):
    includeSearchPaths = everything["includeSearchPaths"]
    for d in includeSearchPaths:
        headerFullpath = os.path.join(d, header)
        if(os.path.exists(headerFullpath)):
            return os.path.normpath(headerFullpath)
    return None

def GetIncludesFromAFile(everything, ppSrcFileFullpath):
    with open(ppSrcFileFullpath, "r") as f:
        lines = f.readlines()
    includes = []
    for line in lines:
        m = re.match(r"#include\s+<(.*)>", line)
        if(not m is None):
            header = m.group(1)
            headerFullpath = ResolveFullPathForHeader(everything, header)
            if(not headerFullpath is None):
                includes.append(headerFullpath)
            else:
                print("[Warning] Header cannot be resolved: {0}".format(header))
                # headers provided by the compiler are not of much interest,
                # they *never* refers back to the zephyer header,
                # but we still need to include them in the graph,
                # so skip parsing them and just use relative path to represent them.
                includes.append(header)
    return includes

def ProcessWorkItem(everything, itemTuple):
    srcFileFullpath = itemTuple[0]
    ppSrcFileFullpath = itemTuple[1]
    includes = []
    if(not ppSrcFileFullpath == "not-resolved-header"):
        includes = GetIncludesFromAFile(everything, ppSrcFileFullpath) # if the header cannot be resolved, the path is not absolute.
        for headerPath in includes: # the headerPath can be absolute, or relative for those headers cannot be resolved.
            AddItemToBacklog(everything, headerPath)
    fromNode = srcFileFullpath
    gm = everything["graphMatrix"]
    gm[fromNode] = includes

    backlog = everything["backlog"]    
    backlog[itemTuple] = True # added to graph!
    return

def DoWork(everything):
    print("Start generating include map for:\n[%s]\n" % everything["srcFileFullpath"])
    GetNinjaBuildFile(everything)
    LoadIncludeSearchPaths(everything)
    LoadConfigMacros(everything)

    AddItemToBacklog(everything, everything["srcFileFullpath"])
    item = GetNextItemFromBacklog(everything)
    while(not item is None):
        ProcessWorkItem(everything, item)
        item = GetNextItemFromBacklog(everything) # item = <srcFileFullpath, preprocessedSrcFile>
        #if (not item[0] in gm.keys()):
            


    print("Finished generating include map for:\n[%s]\n" % everything["srcFileFullpath"])
    return  


def Usage():
    print("\n")
    print("IncludeMap ver 0.1")
    print("By Shao, Ming (smwikipedia@163.com)")
    print("[Description]:")
    print("  This tool generates a map of included headers for a Zephyr source file in the context of a Zephyr build.")
    print("[Pre-condition]:")
    print("  A Zephyr build must be made before using this tool because some build-generated files are needed.")
    print("[Usage]:")
    print("  GenIncludeMap <srcDir> <bldDir> <srcFileFullpath>")
    print("  <srcDir>: the Zephyr source code folder.")
    print("  <bldDir>: the Zephyr build folder where build.ninja file is located.")
    print("  <srcFileFullpath>: the full path Zephyr source file to generate include map for.")
    return


def CleanseArgs(everything):
    return

def IsUnresolvedFile(filePath):
    return not os.path.isabs(filePath)

def IsGeneratedFile(filePath):
    return everything["bldDir"] in filePath

def IsTheStartingNode(filePath):
    return everything["srcFileFullpath"] in filePath

def DetermineNodeLooks(everything, node):
    shape = "oval"
    style = "filled"
    fontName = ""
    if(IsGeneratedFile(node)):            
        nodeText = os.path.relpath(node, everything["bldDir"]).replace("\\", "\n")
        nodeColor = "lightblue"
    elif(IsUnresolvedFile(node)):
        nodeText = node.replace("\\", "\n")
        nodeColor = "lightgrey"
    elif(IsTheStartingNode(node)):
        nodeText = os.path.relpath(node, everything["srcDir"]).replace("\\", "\n")
        shape = "box"
        nodeColor = "green"
        fontName = "bold"
    else:
        nodeText = os.path.relpath(node, everything["srcDir"]).replace("\\", "\n")
        nodeColor = "black"
        style = ""
    return tuple([nodeText, nodeColor, shape, style, fontName])

def GenerateGraph(everything):
    graph = Digraph(engine="dot", comment="Include Map for {0}".format(everything["srcFileFullpath"]))
    gm = everything["graphMatrix"]
    for fromNode in gm.keys():
        looks1 = DetermineNodeLooks(everything, fromNode)
        graph.node(looks1[0], label = looks1[0], color = looks1[1], shape = looks1[2], style = looks1[3], fontname = looks1[4])
        for toNode in gm[fromNode]:
            looks2 = DetermineNodeLooks(everything, toNode)
            graph.edge(looks1[0], looks2[0])
    graphFileName = os.path.basename(everything["srcFileFullpath"])
    graph.render("./IncludeMap_{0}.gv".format(graphFileName), view= False)
    pass

#experimental
def GenerateGraph2(everything):
    graph = Digraph(comment = "Include Map for {0}".format(everything["srcFileFullpath"]))
    gm = everything["graphMatrix"]
    for fromNode in gm.keys():
        subGraphName = os.path.dirname(fromNode).replace("\\", "\\\n")
        with graph.subgraph(name = "cluster_" + subGraphName) as subG:
            subG.attr(style="filled", color = "lightgrey")
            subG.attr(label = subGraphName)
            if(IsGeneratedFile(fromNode)):            
                fromNodeText = os.path.relpath(fromNode, everything["bldDir"]).replace("\\", "\\\n")
                subG.node(fromNodeText, label = fromNodeText, color = "green", style = "filled", shape = "oval")
            elif(IsUnresolvedFile(fromNode)):
                fromNodeText = fromNode.replace("\\", "\\\n")
                subG.node(fromNodeText, label = fromNodeText, color = "red", style = "filled", shape = "oval")
            elif(IsTheStartingNode(fromNode)):
                fromNodeText = os.path.relpath(fromNode, everything["srcDir"]).replace("\\", "\\\n")
                subG.node(fromNodeText, label = fromNodeText, color = "blue", style = "filled", shape = "star")
            else:
                fromNodeText = os.path.relpath(fromNode, everything["srcDir"]).replace("\\", "\\\n")
                subG.node(fromNodeText, label = fromNodeText, color = "black", shape = "oval")
            for toNode in gm[fromNode]:
                if(IsGeneratedFile(toNode)):            
                    toNodeText = os.path.relpath(toNode, everything["bldDir"]).replace("\\", "\\\n")
                elif(IsUnresolvedFile(toNode)):
                    toNodeText = toNode.replace("\\", "\\\n")
                elif(IsTheStartingNode(toNode)):
                    toNodeText = os.path.relpath(toNode, everything["srcDir"]).replace("\\", "\\\n")
                else:
                    toNodeText = os.path.relpath(toNode, everything["srcDir"]).replace("\\", "\\\n")
                subG.edge(fromNodeText, toNodeText)
    graphFileName = os.path.basename(everything["srcFileFullpath"])
    graph.render("./IncludeMap_{0}.gv".format(graphFileName), view= False)
    pass

def CleanUp(everything):
    ppFileList = glob.glob("./pp.*")
    for ppFile in ppFileList:
        os.remove(ppFile)
    return

def OutputIncludeSearchPaths(everything):
    print("The include search paths:")
    for include in everything["includeSearchPaths"]:
        print(os.path.normpath(include))
    return

if __name__=="__main__":
    everything = dict()    
    if(len(sys.argv)!= 4):
        Usage()
    else:
        print("Zephyr Include Map Generator ver 0.1")
        print("By Shao, Ming (smwikipedia@163.com)")
        everything["srcDir"] = os.path.abspath(os.path.normpath(sys.argv[1])) # this is the folder where zephyr source code is located.
        everything["bldDir"] = os.path.abspath(os.path.normpath(sys.argv[2])) # this is the folder where build.ninja file is located.
        everything["srcFileFullpath"] = os.path.abspath(os.path.normpath(sys.argv[3])) # this is the folder to open in VS Code.
        everything["backlog"] = dict()
        # <nodeA, <nodeX, nodeY, nodeZ, ...>>, A connects "to" X, Y, Z, ...
        everything["graphMatrix"] = dict()
        CleanseArgs(everything)
        DoWork(everything)
        GenerateGraph(everything)
        OutputIncludeSearchPaths(everything)
        CleanUp(everything)
    sys.exit(0)