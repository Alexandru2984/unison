import { memo, useEffect, useMemo } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlowProvider,
  useReactFlow,
  type NodeProps,
  type Node,
  type Edge,
} from "reactflow";
import dagre from "dagre";
import "reactflow/dist/style.css";
import { mutationName, type Idea } from "../lib/ideas";
import Icon from "./Icon";

interface CardData {
  idea: Idea;
  saved: boolean;
  count: number;
  horizontal: boolean;
  onBookmark: (idea: Idea) => void;
  onSelect: (idea: Idea) => void;
}
const IdeaCard = memo(function IdeaCard({
  data,
  selected,
}: NodeProps<CardData>) {
  return (
    <div
      className={`idea-node ${data.idea.mutation} ${selected ? "is-selected" : ""}`}
      role="group"
      aria-label={`Idea ${data.idea.id}`}
    >
      <Handle
        type="target"
        position={data.horizontal ? Position.Left : Position.Top}
        isConnectable={false}
      />
      <div className="node-top">
        <span className={`tag ${data.idea.mutation}`}>
          {data.idea.parent_id === null
            ? "Seed idea"
            : mutationName(data.idea.mutation)}
        </span>
        <button
          className={`icon-button tiny nodrag ${data.saved ? "is-saved" : ""}`}
          aria-label={`${data.saved ? "Unsave" : "Save"} idea ${data.idea.id}`}
          aria-pressed={data.saved}
          onClick={(e) => {
            e.stopPropagation();
            data.onBookmark(data.idea);
          }}
        >
          <Icon name="star" size={15} />
        </button>
      </div>
      <button
        className="node-open nodrag"
        onClick={(event) => {
          event.stopPropagation();
          data.onSelect(data.idea);
        }}
      >
        <span className="node-text">{data.idea.content}</span>
        <span className="node-footer">
          <span>#{String(data.idea.id).padStart(3, "0")}</span>
          <span>
            <Icon name="branch" size={13} /> {data.count}{" "}
            {data.count === 1 ? "branch" : "branches"}
          </span>
        </span>
      </button>
      <Handle
        type="source"
        position={data.horizontal ? Position.Right : Position.Bottom}
        isConnectable={false}
      />
    </div>
  );
});
const nodeTypes = { idea: IdeaCard };
function AutoFit({ signature }: { signature: string }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const timer = setTimeout(
      () =>
        void fitView({
          padding: 0.25,
          maxZoom: 1,
          duration: matchMedia("(prefers-reduced-motion: reduce)").matches
            ? 0
            : 300,
        }),
      80,
    );
    return () => clearTimeout(timer);
  }, [signature, fitView]);
  return null;
}
interface Props {
  ideas: Idea[];
  selectedId: number | null;
  bookmarks: number[];
  horizontal: boolean;
  theme: string;
  onSelect: (idea: Idea) => void;
  onBookmark: (idea: Idea) => void;
}
function Graph({
  ideas,
  selectedId,
  bookmarks,
  horizontal,
  theme,
  onSelect,
  onBookmark,
}: Props) {
  const { nodes, edges } = useMemo(() => {
    // A fresh graph prevents stale nodes and edges surviving a filter change.
    const layout = new dagre.graphlib.Graph();
    layout.setDefaultEdgeLabel(() => ({}));
    layout.setGraph({
      rankdir: horizontal ? "LR" : "TB",
      nodesep: 44,
      ranksep: 68,
      marginx: 30,
      marginy: 30,
    });
    const ids = new Set(ideas.map((i) => i.id)),
      counts = new Map<number, number>();
    for (const idea of ideas)
      if (idea.parent_id !== null)
        counts.set(idea.parent_id, (counts.get(idea.parent_id) ?? 0) + 1);
    const graphEdges: Edge[] = [];
    for (const idea of ideas) {
      layout.setNode(String(idea.id), { width: 236, height: 174 });
      if (idea.parent_id !== null && ids.has(idea.parent_id)) {
        layout.setEdge(String(idea.parent_id), String(idea.id));
        graphEdges.push({
          id: `${idea.parent_id}-${idea.id}`,
          source: String(idea.parent_id),
          target: String(idea.id),
          type: "smoothstep",
        });
      }
    }
    dagre.layout(layout);
    const graphNodes: Node<CardData>[] = ideas.map((idea) => {
      const point = layout.node(String(idea.id));
      return {
        id: String(idea.id),
        type: "idea",
        position: { x: point.x - 118, y: point.y - 87 },
        data: {
          idea,
          saved: bookmarks.includes(idea.id),
          count: counts.get(idea.id) ?? 0,
          horizontal,
          onBookmark,
          onSelect,
        },
        focusable: false,
        selected: idea.id === selectedId,
        sourcePosition: horizontal ? Position.Right : Position.Bottom,
        targetPosition: horizontal ? Position.Left : Position.Top,
      };
    });
    return { nodes: graphNodes, edges: graphEdges };
  }, [ideas, selectedId, bookmarks, horizontal, onBookmark, onSelect]);
  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodeClick={(_, node) => onSelect(node.data.idea)}
      nodesConnectable={false}
      nodesDraggable={false}
      edgesFocusable={false}
      deleteKeyCode={null}
      selectionKeyCode={null}
      multiSelectionKeyCode={null}
      minZoom={0.12}
      maxZoom={1.7}
      fitView
      fitViewOptions={{ padding: 0.25, maxZoom: 1 }}
      onlyRenderVisibleElements
      proOptions={{ hideAttribution: false }}
      aria-label="Interactive idea evolution graph"
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={22}
        size={1}
        color={theme === "dark" ? "#2c443a" : "#d8dfd7"}
      />
      <Controls showInteractive={false} />
      <MiniMap
        className="graph-minimap"
        pannable
        zoomable
        nodeColor={(node) =>
          node.selected ? "#568158" : theme === "dark" ? "#3c5447" : "#c6d4c2"
        }
        maskColor={theme === "dark" ? "#142019bb" : "#f5f7f3bb"}
      />
      <AutoFit signature={ideas.map((i) => i.id).join(",") + horizontal} />
    </ReactFlow>
  );
}
export default function IdeaGraph(props: Props) {
  return (
    <ReactFlowProvider>
      <Graph {...props} />
    </ReactFlowProvider>
  );
}
