import unittest

import keepsync_notes as app
import keepsync_tag_graph as tag_graph


class TagGraphTests(unittest.TestCase):
    def test_build_tag_graph_counts_nodes_and_shared_edges(self):
        graph = tag_graph.build_tag_graph([
            app.Note(id="a", title="A", content="", labels=["work", "client", "urgent"]),
            app.Note(id="b", title="B", content="", labels=["work", "client"]),
            app.Note(id="c", title="C", content="", labels=["personal"]),
        ])

        node_counts = {node.label: node.count for node in graph.nodes}
        edge_counts = {(edge.left, edge.right): edge.count for edge in graph.edges}

        self.assertEqual(node_counts["work"], 2)
        self.assertEqual(node_counts["client"], 2)
        self.assertEqual(node_counts["personal"], 1)
        self.assertEqual(edge_counts[("client", "work")], 2)
        self.assertEqual(edge_counts[("client", "urgent")], 1)

    def test_summary_handles_empty_and_connected_graphs(self):
        self.assertEqual(tag_graph.tag_graph_summary_lines(tag_graph.build_tag_graph([])), ["No labeled notes yet."])

        graph = tag_graph.build_tag_graph([
            app.Note(id="a", title="A", content="", labels=["alpha", "beta"]),
        ])
        summary = "\n".join(tag_graph.tag_graph_summary_lines(graph))

        self.assertIn("alpha + beta: 1 note", summary)

    def test_app_reexports_tag_graph_helpers_for_compatibility(self):
        self.assertIs(app.build_tag_graph, tag_graph.build_tag_graph)
        self.assertIs(app.tag_graph_summary_lines, tag_graph.tag_graph_summary_lines)
        self.assertIs(app.TagGraph, tag_graph.TagGraph)


if __name__ == "__main__":
    unittest.main()
