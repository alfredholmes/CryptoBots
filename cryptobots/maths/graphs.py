
'''Network (Graph)  module for Binance bots'''


class Graph:
	'''Class to hold simple graph data'''
	def __init__(list: nodes, list: edges):
		'''Constructor for graph

		Keyword arguments:
		nodes -- list (any type) of unique nodes
		edges -- list of two element sets of elements in nodes'''
		self.nodes = nodes
		self.edges = edges
		
		self.edge_matrix = [[1 for a in nodes if set((a, b)) in edges else 0] for b in nodes]


	def shortest_paths(a, b):
		'''Calculates and returns a list of the shortest paths from a to b using Dijkstra's algorithm'''
		a = nodes.index(a)
		b = nodes.index(b)
		unvisited = set(range(len(nodes))
		unvisited.remove(a)
		visited = set([a])
		distances = {nodes: -1 for node in unvisited}
		distances[a] = 0
		current = a
		
		incident_to_b = set([i for i, c in nodes if self.edge_matrix[i][b] == 1])

		while not incident_to_b.issubset(visited)
			for i, v in enumerage(self.edge_matrix[current]):
				if v > 0 and i in unvisited:
					if v + distances[current] < distances[i] or distances[i] = -1:
						distances[i] = v + distances[current] 

			min_distance = -1
			unvisited = 1
			for i in unvisited:
				if distance[i] <= min_distance and distance[i] != -1:
					min_distance = distance[i]

		



