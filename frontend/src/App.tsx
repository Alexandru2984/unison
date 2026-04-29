import { useState, useEffect } from 'react';
import ReactFlow, { MiniMap, Controls, Background, useNodesState, useEdgesState } from 'reactflow';
import 'reactflow/dist/style.css';
import axios from 'axios';

const API_URL = "/api";
const WS_URL = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + "/ws";

interface Idea {
  id: number;
  parent_id: number | null;
  content: string;
  mutation: string;
}

const App = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [input, setInput] = useState('');
  const [selectedParent, setSelectedParent] = useState<number | null>(null);

  const fetchIdeas = async () => {
    try {
      const res = await axios.get<Idea[]>(`${API_URL}/idea`);
      const { newNodes, newEdges } = formatGraph(res.data);
      setNodes(newNodes as any);
      setEdges(newEdges);
    } catch (e) {
      console.error("Failed to fetch ideas", e);
    }
  };

  const formatGraph = (ideas: Idea[]) => {
    const newNodes = ideas.map((idea, index) => ({
      id: idea.id.toString(),
      position: { x: (index % 3) * 250, y: Math.floor(index / 3) * 150 },
      data: { label: `${idea.mutation !== 'base' ? '[' + idea.mutation + ']' : ''} ${idea.content}` },
      style: { border: selectedParent === idea.id ? '2px solid blue' : '1px solid #222' }
    }));

    const newEdges = ideas
      .filter(i => i.parent_id !== null)
      .map(i => ({
        id: `e${i.parent_id}-${i.id}`,
        source: i.parent_id!.toString(),
        target: i.id.toString(),
        animated: true,
      }));

    return { newNodes, newEdges };
  };

  useEffect(() => {
    fetchIdeas();
    
    const ws = new WebSocket(WS_URL);
    ws.onmessage = () => {
      fetchIdeas(); // Refresh graph completely on new message
    };
    return () => ws.close();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const submitIdea = async (mutation: string = 'base') => {
    if (!input && mutation === 'base') return;
    try {
      const parent_content = nodes.find((n: any) => n.id === selectedParent?.toString())?.data.label || "";
      await axios.post(`${API_URL}/idea`, {
        content: mutation === 'base' ? input : parent_content.replace(/^\[.*?\] /, ''),
        parent_id: selectedParent,
        mutation
      });
      setInput('');
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '20px', background: '#282c34', color: 'white' }}>
        <h1>Distributed Idea Evolution Engine</h1>
        <p>Built with Unison. Select a node to mutate it.</p>
        <div style={{ display: 'flex', gap: '10px' }}>
          <input 
            value={input} 
            onChange={e => setInput(e.target.value)} 
            placeholder="New Base Idea..." 
          />
          <button onClick={() => submitIdea('base')}>Submit Base Idea</button>
          
          <button onClick={() => submitIdea('expand')} disabled={!selectedParent}>Expand</button>
          <button onClick={() => submitIdea('rephrase')} disabled={!selectedParent}>Rephrase</button>
          <button onClick={() => submitIdea('mutate_keywords')} disabled={!selectedParent}>Mutate</button>
        </div>
      </header>
      
      <div style={{ flex: 1 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={(_, node) => setSelectedParent(Number(node.id))}
          fitView
        >
          <Controls />
          <MiniMap />
          <Background gap={12} size={1} />
        </ReactFlow>
      </div>
    </div>
  );
};

export default App;
