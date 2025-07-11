from queue import PriorityQueue

# --- A* Implementation (provided) ---
class AStarNode:
    def __init__(self, data, predecessor=None):
        self.data = data
        self.predecessor = predecessor
        self.g = 0
        self.h = 0
        self.f = 0
    def __lt__(self, other):
        return self.f < other.f


def astar(start, end, successors, h):
    open_pqueue = PriorityQueue()
    open_pqueue.put(AStarNode(start))
    best_g = dict()
    closed = set()
    
    while not open_pqueue.empty():
        current = open_pqueue.get()
        if current.data in closed:
            continue
        closed.add(current.data)
        
        if end(current.data):
            path = []
            while current:
                path.append(current.data)
                current = current.predecessor
            return path[::-1]
        
        for successor, cost in successors(current.data):
            if successor in closed:
                continue
            node = AStarNode(successor, predecessor=current)
            node.g = current.g + cost
            node.h = h(successor)
            node.f = node.g + node.h
            
            if successor in best_g and node.g >= best_g[successor]:
                continue
            
            open_pqueue.put(node)
            best_g[successor] = node.g
    return None
