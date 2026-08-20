let mapData = null;

// LOAD MAP DATA FROM FLASK
async function loadMapData()
{
    try
    {
        const response = await fetch("/api/map");

        if (!response.ok)
        {
            throw new Error("Failed to load map data.");
        }

        mapData = await response.json();

        console.log("Map data loaded:");
        console.log(mapData);

        const overlay = document.getElementById("map-overlay");

        overlay.setAttribute("viewbox", '0 0 ${mapData.image.width} ${mapData.image.height}');

        drawNavigationNetwork();
    }
    catch (error)
    {
        console.error("Error loading map:", error);
    }
}

// DRAW NAVIGATION NETWORK
function drawNavigationNetwork()
{
    const nodesGroup = document.getElementById("navigation-nodes");
    const linesGroup = document.getElementById("navigation-lines");

    // clear previous drawings
    nodesGroup.innerHTML ="";
    linesGroup.innerHTML = "";

    // TEMPORARY (2 consoles)
    console.log("Number of nodes:", Object.keys(mapData.nodes).length);
    console.log("Number of connections:", mapData.connections.length);

    console.log("Nodes group:", nodesGroup);
    console.log("Lines group:", linesGroup);

    // DRAW CONNECTIONS
    mapData.connections.forEach(connection => {
        const startNodeId = connection[0];
        const endNodeId = connection[1];

        const startNode = mapData.nodes[startNodeId];
        const endNode = mapData.nodes[endNodeId];
        
        if (!startNode || !endNode)
        {
            console.warn("Missing node:", startNodeId, endNodeId);
            return;
        }

        const line = document.createElementNS("http://www.w3.org/2000/svg",
                "line");

        line.setAttribute("x1", startNode.x);
        line.setAttribute("y1", startNode.y);

        line.setAttribute("x2", endNode.x);
        line.setAttribute("y2", endNode.y);

        line.classList.add("navigation-line");

        linesGroup.appendChild(line);
    });

    // DRAW NODES
    Object.entries(mapData.nodes).forEach(
        ([nodeId, node]) => {
            const circle = document.createElementNS("http://www.w3.org/2000/svg",
                    "circle");

            circle.setAttribute("cx", node.x);
            circle.setAttribute("cy", node.y);

            circle.setAttribute("r", "6");
            circle.classList.add("navigation-node");

            nodesGroup.appendChild(circle);

            // NODE LABEL
            const label = document.createElementNS("http://www.w3.org/2000/svg",
                        "text");
            
            label.setAttribute("x", node.x + 8);
            label.setAttribute("y", node.y - 8);

            label.classList.add("navigation-node-label");

            label.textContent = nodeId.replace("node_", "N");

            nodesGroup.appendChild(label);
        }
    );
}

// START APPLICATION
document.addEventListener("DOMContentLoaded", 
    function() {
        console.log("Dpulze navigation application started.");

        loadMapData();
    });