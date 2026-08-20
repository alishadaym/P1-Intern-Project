let mapData = null;
let selectedShopId = null;

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
        drawUserMarker();
        populateShopDropdown();
        drawPOIMarkers();
        drawShopHotspots();
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
document.addEventListener("DOMContentLoaded", async function()
{
    console.log("Dpulze navigation applicaiton started.");

    await loadMapData();

    // NAVIGATE BUTTON
    const navigateButton = document.getElementById("navigate-btn");

    if (navigateButton)
    {
        navigateButton.addEventListener("click", startNavigation);
        console.log("Navigate button ready.");
    }
    else
    {
        console.error("Navigate button not found.");
    }

    // SHOP DROPDOWN
    const shopSelect = document.getElementById("shop-select");

    shopSelect.addEventListener(
        "change",
        function () {
            if (shopSelect.value) {
                selectShop(shopSelect.value);
            }
        }
    );
});

// DRAW USER CURRENT LOCATION
function drawUserMarker()
{
    const userMarker = document.getElementById("user-marker");

    //guest starts at Main Entrance
    const startNodeId = "node_01";
    const startNode = mapData.nodes[startNodeId];

    if (!startNode)
    {
        console.error("User start node not found:", startNodeId);
        return;
    }

    userMarker.setAttribute("cx", startNode.x);
    userMarker.setAttribute("cy", startNode.y);

    console.log("User location:", startNodeId);
};

// SHOP DROPDOWN
function populateShopDropdown()
{
    const shopSelect = document.getElementById("shop-select");

    shopSelect.innerHTML = "";

    // default option
    const defaultOption = document.createElement("option");

    defaultOption.value = "";
    defaultOption.textContent = "Select a shop";

    shopSelect.appendChild(defaultOption);

    // ADD SHOPS
    Object.entries(mapData.shop_locations).forEach(
        ([shopId, shop]) => {
            const option = document.createElement("option");

            option.value = shopId;

            // convert shop name
            const shopName = shopId.replace(/_\d+$/, "").replace(/_/g, " ").replace(/\b\w/g, letter => letter.toUpperCase());

            option.textContent = shopName;

            shopSelect.appendChild(option);
        }
    );
}

// FIND SHORTEST PATH (DIJKSTRA)
function findShortestPath(startNodeId, endNodeId)
{
    console.log(
        "Finding shortest-distance route from:",
        startNodeId,
        "to:",
        endNodeId
    );

    const distances = {};
    const previous = {};
    const unvisited = new Set();

    // Initialize all nodes
    Object.keys(mapData.nodes).forEach(nodeId =>
    {
        distances[nodeId] = Infinity;
        previous[nodeId] = null;
        unvisited.add(nodeId);
    });

    distances[startNodeId] = 0;

    while (unvisited.size > 0)
    {
        let currentNode = null;
        let smallestDistance = Infinity;

        // Find unvisited node with smallest known distance
        unvisited.forEach(nodeId =>
        {
            if (distances[nodeId] < smallestDistance)
            {
                smallestDistance = distances[nodeId];
                currentNode = nodeId;
            }
        });

        // No remaining reachable nodes
        if (currentNode === null)
        {
            break;
        }

        // Destination reached
        if (currentNode === endNodeId)
        {
            break;
        }

        unvisited.delete(currentNode);

        // Find neighbours of current node
        mapData.connections.forEach(connection =>
        {
            const nodeA = connection[0];
            const nodeB = connection[1];

            let neighbour = null;

            if (nodeA === currentNode)
            {
                neighbour = nodeB;
            }
            else if (nodeB === currentNode)
            {
                neighbour = nodeA;
            }

            if (!neighbour || !unvisited.has(neighbour))
            {
                return;
            }

            const currentPosition =
                mapData.nodes[currentNode];

            const neighbourPosition =
                mapData.nodes[neighbour];

            // Euclidean distance
            const dx =
                neighbourPosition.x - currentPosition.x;

            const dy =
                neighbourPosition.y - currentPosition.y;

            const edgeDistance =
                Math.sqrt(
                    (dx * dx) + (dy * dy)
                );

            const newDistance =
                distances[currentNode] + edgeDistance;

            if (newDistance < distances[neighbour])
            {
                distances[neighbour] =
                    newDistance;

                previous[neighbour] =
                    currentNode;
            }
        });
    }

    // No route found
    if (distances[endNodeId] === Infinity)
    {
        console.error(
            "No route found between",
            startNodeId,
            "and",
            endNodeId
        );

        return null;
    }

    // Reconstruct route
    const path = [];

    let currentNode = endNodeId;

    while (currentNode !== null)
    {
        path.unshift(currentNode);

        currentNode =
            previous[currentNode];
    }

    if (path[0] !== startNodeId)
    {
        console.error("Route reconstruction failed.");
        return null;
    }

    console.log(
        "Shortest-distance route:",
        path
    );

    console.log(
        "Total route distance:",
        distances[endNodeId]
    );

    return path;
}

// DRAW ROUTE ON MAP
function drawRoute(path)
{
    const routeLine =
        document.getElementById("route-line");

    if (!path || path.length === 0)
    {
        routeLine.setAttribute("points", "");
        return;
    }

    const points = path.map(nodeId =>
    {
        const node = mapData.nodes[nodeId];

        if (!node)
        {
            return null;
        }

        return `${node.x},${node.y}`;
    })
    .filter(point => point !== null)
    .join(" ");

    routeLine.setAttribute("points", points);

    console.log("Route drawn:", path);
}

// START NAVIGATION
function startNavigation()
{
    const shopSelect =
        document.getElementById("shop-select");


    // Shop can be selected either by:
    // 1. clicking map
    // 2. using dropdown
    const chosenShopId =
        selectedShopId || shopSelect.value;


    if (!chosenShopId)
    {
        alert("Please select a shop.");
        return;
    }


    const selectedShop =
        mapData.shop_locations[chosenShopId];


    if (!selectedShop)
    {
        console.error(
            "Selected shop not found:",
            chosenShopId
        );

        return;
    }


    const startNodeId = "node_01";

    const destinationNodeId =
        selectedShop.node_id;


    console.log("Selected shop:", chosenShopId);
    console.log("Start:", startNodeId);
    console.log("Destination:", destinationNodeId);


    const path =
        findShortestPath(startNodeId, destinationNodeId);


    if (!path)
    {
        alert("No route found.");
        return;
    }

    drawRoute(path);
}

// DRAW POINT OF INTEREST (POI)
function createPOIMarker(poiId, poi)
{
    const poiGroup = document.getElementById("poi-markers");

    if (poi.x === undefined || poi.y === undefined)
    {
        console.warn("POI coordinates missing:", poiId);
        return;
    }

    const marker = document.createElementNS("http://www.w3.org/2000/svg",
            "circle");

    marker.setAttribute("cx", poi.x);
    marker.setAttribute("cy", poi.y);
    marker.setAttribute("r", "10");

    marker.classList.add("poi-marker");

    marker.dataset.poiId = poiId;
    marker.dataset.poiType = poi.type;

     marker.addEventListener(
        "click",
        function () {
            selectShop(poiId);
    });

    poiGroup.appendChild(marker);

    // const label = document.createElementNS("http://www.w3.org/2000/svg",
    //         "text");

    // label.setAttribute("x", poi.x + 14);
    // label.setAttribute("y", poi.y + 4);

    // label.textContent = poi.name;

    // label.classList.add("poi-label");

    // poiGroup.appendChild(label);
}

function drawPOIMarkers()
{
    const poiGroup = document.getElementById("poi-markers");

    poiGroup.innerHTML = "";

    Object.entries(mapData.shop_locations).forEach(
        ([shopId, shop]) =>
        {
            createPOIMarker(shopId, shop);
        }
    );

    if (mapData.facilities)
    {
        Object.entries(mapData.facilities).forEach(
            ([facilityId, facility]) =>
            {
                createPOIMarker(facilityId, facility);
            }
        );
    }
}

// DETAILS OF SHOP POP UP
function drawShopHotspots()
{
    const hotspotGroup =
        document.getElementById("shop-hotspots");

    hotspotGroup.innerHTML = "";

    Object.entries(mapData.shop_locations).forEach(
        ([shopId, shop]) =>
        {
            if (!shop.hotspot)
            {
                return;
            }

            const hotspot =
                document.createElementNS(
                    "http://www.w3.org/2000/svg",
                    "rect"
                );

            hotspot.setAttribute(
                "x",
                shop.hotspot.x
            );

            hotspot.setAttribute(
                "y",
                shop.hotspot.y
            );

            hotspot.setAttribute(
                "width",
                shop.hotspot.width
            );

            hotspot.setAttribute(
                "height",
                shop.hotspot.height
            );

            hotspot.classList.add("shop-hotspot");

            hotspot.dataset.shopId = shopId;

            hotspot.addEventListener(
                "click",
                function()
                {
                    selectShop(shopId);
                }
            );

            hotspotGroup.appendChild(hotspot);
        }
    );
}

// SELECT SHOP
function selectShop(shopId)
{
    const shop = mapData.shop_locations[shopId];

    if (!shop)
    {
        console.error("Shop not found:", shopId);
        return;
    }

    selectedShopId = shopId;

    // Synchronise dropdown
    const shopSelect =
        document.getElementById("shop-select");

    shopSelect.value = shopId;

    // Update Selected Shop panel
    updateSelectedShopPanel(shopId, shop);

    // Highlight selected shop
    highlightSelectedShop(shopId);
}

// UPDATE SELECTED SHOP PANEL
function updateSelectedShopPanel(shopId, shop)
{
    const panel =
        document.getElementById(
            "selected-shop-details"
        );

    panel.innerHTML = `
        <div class="shop-details-card">

            <strong class="shop-details-name">
                ${shop.name}
            </strong>

            ${
                shop.category
                ? `<div>${shop.category}</div>`
                : ""
            }

            ${
                shop.floor
                ? `<div>${shop.floor}</div>`
                : ""
            }

            ${
                shop.opening_hours
                ? `<div>Hours: ${shop.opening_hours}</div>`
                : ""
            }

        </div>
    `;
}

// HIGHLIGHT SELECTED SHOP
function highlightSelectedShop(shopId)
{
    // Remove previous highlight
    document
        .querySelectorAll(".poi-marker")
        .forEach(marker =>
        {
            marker.classList.remove(
                "poi-selected"
            );
        });


    // Find selected marker
    const selectedMarker =
        document.querySelector(
            `.poi-marker[data-poi-id="${shopId}"]`
        );


    if (selectedMarker)
    {
        selectedMarker.classList.add(
            "poi-selected"
        );
    }
}