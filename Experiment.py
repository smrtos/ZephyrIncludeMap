from graphviz import Digraph
dot = Digraph(comment="The Round Table")
dot.node("tom", Label = "Tangseng1")
dot.node("bob", "Wukong")
dot.node("lucy", "Bajie")

dot.edges([("tom", "bob"), ("bob", "lucy")])
dot.edge("tom", "lucy", constraint="false")

print(dot.source)

dot.render("./xiyouji.gv", view= False)