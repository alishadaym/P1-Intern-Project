let mapData = null;
let selectedShopId = null;
let shopDatabase = {};
let shopRecords = [];
let categoryNames = [];
let selectedDestination = null;
let utilityRecords = [];
let selectedUtilityId = null;

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

        overlay.setAttribute("viewBox", `0 0 ${mapData.image.width} ${mapData.image.height}`);

        drawNavigationNetwork();
        drawUserMarker();
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
    await loadUtilities();
    drawPOIMarkers();
    await loadShopDatabase();
    await loadCategories();
    populateShopDropdown();
    populateCategoryDropdown();

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

    // SHOP DROPDOWN (kept in the DOM, hidden - still the source of truth
    // that selectShop() and startNavigation() read/write)
    const shopSelect = document.getElementById("shop-select");

    shopSelect.addEventListener(
        "change",
        function () {
            if (shopSelect.value) {
                selectShop(shopSelect.value);
            }
        }
    );

    // SHOP SEARCH (type-ahead combobox)
    const shopSearch = document.getElementById("shop-search");
    const shopSuggestions = document.getElementById("shop-suggestions");

    if (shopSearch && shopSuggestions)
    {
        shopSearch.addEventListener(
            "input",
            function () {
                renderShopSuggestions(shopSearch.value);
            }
        );

        shopSearch.addEventListener(
            "focus",
            function () {
                renderShopSuggestions(shopSearch.value);
            }
        );

        shopSearch.addEventListener("keydown", handleShopSearchKeydown);

        document.addEventListener(
            "click",
            function (event) {
                if (!event.target.closest(".shop-autocomplete"))
                {
                    hideShopSuggestions();
                }
            }
        );
    }

    document
        .getElementById("category-select")
        .addEventListener("change", renderCategoryShops);

    document
        .getElementById("utility-select")
        .addEventListener("change", renderUtilityLocations);

    const shopModal = document.getElementById("shop-modal");
    const closeShopModal = document.getElementById("close-shop-modal");
    const utilityModal = document.getElementById("utility-modal");
    const closeUtilityModal = document.getElementById("close-utility-modal");

    closeShopModal.addEventListener("click", closeShopDetails);
    closeUtilityModal.addEventListener("click", closeUtilityDetails);
    shopModal.addEventListener("click", function(event)
    {
        if (event.target === shopModal)
        {
            closeShopDetails();
        }
    });
    utilityModal.addEventListener("click", function(event)
    {
        if (event.target === utilityModal)
        {
            closeUtilityDetails();
        }
    });
    document.addEventListener("keydown", function(event)
    {
        if (event.key === "Escape" && !shopModal.hidden)
        {
            closeShopDetails();
        }
        if (event.key === "Escape" && !utilityModal.hidden)
        {
            closeUtilityDetails();
        }
    });
});

let lastShopTrigger = null;

function closeShopDetails()
{
    const shopModal = document.getElementById("shop-modal");
    shopModal.hidden = true;

    if (lastShopTrigger)
    {
        lastShopTrigger.focus();
        lastShopTrigger = null;
    }
}

function showShopDetails(shop)
{
    const shopModal = document.getElementById("shop-modal");

    lastShopTrigger = document.activeElement;
    document.getElementById("modal-shop-name").textContent = shop.name || "Unnamed Shop";
    document.getElementById("modal-shop-category").textContent = shop.category || "";
    document.getElementById("modal-shop-unit").textContent = shop.unit ? `Unit: ${shop.unit}` : "";
    document.getElementById("modal-shop-floor").textContent = shop.floor || "";
    document.getElementById("modal-shop-hours").textContent = shop.operatingHours ? `Hours: ${shop.operatingHours}` : "";
    document.getElementById("modal-shop-description").textContent = shop.description || "";
    shopModal.hidden = false;
    document.getElementById("close-shop-modal").focus();
}

function closeUtilityDetails()
{
    document.getElementById("utility-modal").hidden = true;
    resetUtilityMapZoom();
}

function showUtilityDetails(utility)
{
    const utilityModal = document.getElementById("utility-modal");
    const mapContainer = document.querySelector(".map-container");
    const status = getUtilityStatusLabel(utility);

    document.getElementById("modal-utility-name").textContent = utility.name;
    document.getElementById("modal-utility-floor").textContent = `Floor: ${utility.floor}`;
    document.getElementById("modal-utility-status").textContent = status
        ? status
        : "Location available";
    const originX = utility.x / mapData.image.width * 100;
    const originY = utility.y / mapData.image.height * 100;
    mapContainer.style.transformOrigin = `${originX}% ${originY}%`;
    mapContainer.classList.add("utility-zoomed");
    utilityModal.hidden = false;
    positionUtilityModal(utility.utility_code);
    document.getElementById("close-utility-modal").focus();
}

function positionUtilityModal(utilityId)
{
    requestAnimationFrame(function()
    {
        const utilityModal = document.getElementById("utility-modal");
        const utilityContent = utilityModal.querySelector(".utility-modal-content");
        const marker = Array.from(document.querySelectorAll("#poi-markers circle"))
            .find(item => item.dataset.poiId === String(utilityId));

        if (!marker)
        {
            return;
        }

        const markerBounds = marker.getBoundingClientRect();
        const contentBounds = utilityContent.getBoundingClientRect();
        const margin = 12;
        let left = markerBounds.right + margin;
        let top = markerBounds.top + (markerBounds.height - contentBounds.height) / 2;

        utilityContent.classList.remove("left");
        if (left + contentBounds.width > window.innerWidth - margin)
        {
            left = markerBounds.left - contentBounds.width - margin;
            utilityContent.classList.add("left");
        }

        left = Math.max(margin, Math.min(left, window.innerWidth - contentBounds.width - margin));
        top = Math.max(margin, Math.min(top, window.innerHeight - contentBounds.height - margin));

        utilityContent.style.left = `${left}px`;
        utilityContent.style.top = `${top}px`;
    });
}

function resetUtilityMapZoom()
{
    const mapContainer = document.querySelector(".map-container");

    if (mapContainer)
    {
        mapContainer.classList.remove("utility-zoomed");
        mapContainer.style.transformOrigin = "";
    }
}

// DRAW USER CURRENT LOCATION
function drawUserMarker()
{
    const userMarker = document.getElementById("user-marker");

    // Set by the last scanned QR code; falls back to Main Entrance for guests
    const startNodeId = window.START_NODE_ID || "node_01";
    const startNode = mapData.nodes[startNodeId];

    if (!startNode)
    {
        console.error("User start node not found:", startNodeId);
        return;
    }

    // Anchor the pin's bottom tip (not its top-left corner) to the node
    const pinWidth = Number(userMarker.getAttribute("width"));
    const pinHeight = Number(userMarker.getAttribute("height"));

    userMarker.setAttribute("x", startNode.x - pinWidth / 2);
    userMarker.setAttribute("y", startNode.y - pinHeight);

    console.log("User location:", startNodeId);
};

// SHOP LABEL (display name, preferring live DB data over the map's own data)
function getShopLabel(shopId)
{
    const shop = mapData.shop_locations[shopId];
    const dbShop = shopDatabase[shopId];

    return (
        (dbShop && dbShop.display_name) ||
        (shop && shop.name) ||
        shopId.replace(/_\d+$/, "").replace(/_/g, " ").replace(/\b\w/g, letter => letter.toUpperCase())
    );
}

async function loadUtilities()
{
    const response = await fetch("/api/utilities");

    if (!response.ok)
    {
        throw new Error("Failed to load utilities.");
    }

    utilityRecords = await response.json();
    mapData.facilities = Object.fromEntries(
        utilityRecords.map(utility => [utility.utility_code, utility])
    );
}

function getUtilityStatusLabel(utility)
{
    if (utility.type === "restroom")
    {
        return `Available: ${utility.available_cubicles} | Occupied: ${utility.occupied_cubicles}`;
    }

    if (utility.type === "oku")
    {
        return utility.is_occupied ? "Occupied" : "Available";
    }

    return "";
}

function renderUtilityLocations()
{
    const utilityType = document.getElementById("utility-select").value;
    const utilityList = document.getElementById("utility-list");

    utilityList.innerHTML = "";

    if (!utilityType)
    {
        utilityList.textContent = "Choose a utility to see locations";
        return;
    }

    const matchingUtilities = Object.entries(mapData.facilities || {})
        .filter(([, utility]) => utility.type === utilityType);

    if (matchingUtilities.length === 0)
    {
        utilityList.textContent = "No locations found";
        return;
    }

    matchingUtilities.forEach(([utilityId, utility]) =>
    {
        const utilityButton = document.createElement("button");
        const statusLabel = getUtilityStatusLabel(utility);

        utilityButton.type = "button";
        utilityButton.className = "utility-list-item";
        utilityButton.dataset.utilityId = utilityId;
        if (utilityId === selectedUtilityId)
        {
            utilityButton.classList.add("selected");
        }
        const locationLabel = statusLabel
            ? `${utility.floor} - ${statusLabel}`
            : utility.floor;
        utilityButton.innerHTML = `${utility.name}<span class="utility-status">${locationLabel}</span>`;
        utilityButton.addEventListener("click", function()
        {
            selectUtility(utilityId);
        });

        utilityList.appendChild(utilityButton);
    });
}

// SHOP DROPDOWN (hidden - always holds every shop, kept in sync with
// whichever shop is currently selected)
function populateShopDropdown()
{
    const shopSelect =
        document.getElementById("shop-select");

    shopSelect.innerHTML =
        `<option value="">Select a shop</option>`;

    Object.keys(mapData.shop_locations).forEach(
        shopId =>
        {
            const option =
                document.createElement("option");

            option.value = shopId;
            option.textContent = getShopLabel(shopId);

            shopSelect.appendChild(option);
        }
    );
}

// CATEGORY FILTER
function populateCategoryDropdown() {
    const categorySelect = document.getElementById("category-select");
    categorySelect.innerHTML = "<option value=\"\">All categories</option>";

    categoryNames
        .forEach(category => {
            const option = document.createElement("option");
            option.value = category;
            option.textContent = category;
            categorySelect.appendChild(option);
        });
}

function renderCategoryShops() {
    const category = document.getElementById("category-select").value;
    const shopList = document.getElementById("category-shop-list");

    if (!category) {
        shopList.textContent = "Choose a category";
        return;
    }

    const matchingShops = shopRecords
        .filter(shop => shop.category && shop.category.trim() === category)
        .sort((firstShop, secondShop) => {
            const firstName = firstShop.shop_name || "";
            const secondName = secondShop.shop_name || "";
            return firstName.localeCompare(secondName);
        });

    shopList.innerHTML = "";

    if (matchingShops.length === 0) {
        shopList.textContent = "No shops found in this category";
        return;
    }

    matchingShops.forEach(shop => {
        const shopButton = document.createElement("button");

        shopButton.type = "button";
        shopButton.className = "category-shop-item";
        shopButton.textContent = shop.shop_name || "Unnamed Shop";

        if (mapData.shop_locations[shop.shop_code]) {
            shopButton.addEventListener("click", () => selectShop(shop.shop_code));
        }
        else {
            shopButton.disabled = true;
            shopButton.title = "This shop has no map location yet";
        }

        shopList.appendChild(shopButton);
    });
}

// SHOP SEARCH SUGGESTIONS
let activeSuggestionIndex = -1;

function renderShopSuggestions(searchText)
{
    const shopSuggestions =
        document.getElementById("shop-suggestions");

    const query = (searchText || "").trim().toLowerCase();
    activeSuggestionIndex = -1;

    // Empty query -> show every shop (e.g. right when the box is focused)
    const matches =
        Object.keys(mapData.shop_locations)
            .map(shopId => ({ shopId, label: getShopLabel(shopId) }))
            .filter(({ label }) => label.toLowerCase().includes(query));

    shopSuggestions.innerHTML = "";

    if (matches.length === 0)
    {
        const noResults = document.createElement("li");
        noResults.className = "no-results";
        noResults.textContent = "No shops found";
        shopSuggestions.appendChild(noResults);
    }
    else
    {
        matches.forEach(({ shopId, label }) =>
        {
            const item = document.createElement("li");
            item.textContent = label;
            item.dataset.shopId = shopId;

            item.addEventListener(
                "click",
                function () {
                    chooseShop(shopId, label);
                }
            );

            shopSuggestions.appendChild(item);
        });
    }

    shopSuggestions.classList.add("visible");
}

function hideShopSuggestions()
{
    const shopSuggestions =
        document.getElementById("shop-suggestions");

    shopSuggestions.classList.remove("visible");
    activeSuggestionIndex = -1;
}

function chooseShop(shopId, label)
{
    const shopSearch =
        document.getElementById("shop-search");

    shopSearch.value = label;
    hideShopSuggestions();
    selectShop(shopId);
}

function handleShopSearchKeydown(event)
{
    const shopSuggestions =
        document.getElementById("shop-suggestions");

    const items =
        Array.from(shopSuggestions.querySelectorAll("li:not(.no-results)"));

    if (!shopSuggestions.classList.contains("visible") || items.length === 0)
    {
        return;
    }

    if (event.key === "ArrowDown")
    {
        event.preventDefault();
        activeSuggestionIndex = (activeSuggestionIndex + 1) % items.length;
    }
    else if (event.key === "ArrowUp")
    {
        event.preventDefault();
        activeSuggestionIndex = (activeSuggestionIndex - 1 + items.length) % items.length;
    }
    else if (event.key === "Enter")
    {
        event.preventDefault();

        const chosen = activeSuggestionIndex >= 0 ? items[activeSuggestionIndex] : items[0];
        chooseShop(chosen.dataset.shopId, chosen.textContent);
        return;
    }
    else if (event.key === "Escape")
    {
        hideShopSuggestions();
        return;
    }
    else
    {
        return;
    }

    items.forEach(item => item.classList.remove("active"));
    items[activeSuggestionIndex].classList.add("active");
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
    if (!selectedDestination)
    {
        alert("Please select a shop or utility.");
        return;
    }

    if (!mapData.nodes[selectedDestination.nodeId])
    {
        console.error(
            "Destination node not found:",
            selectedDestination.nodeId
        );

        return;
    }


    const startNodeId = window.START_NODE_ID || "node_01";

    const destinationNodeId = selectedDestination.nodeId;


    console.log("Selected destination:", selectedDestination.label);
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
            if (mapData.shop_locations[poiId])
            {
                selectShop(poiId);
            }
            else if (mapData.facilities && mapData.facilities[poiId])
            {
                showUtilityDetails(mapData.facilities[poiId]);
            }
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
    const poiGroup =
        document.getElementById("poi-markers");

    poiGroup.innerHTML = "";

    // DO NOT draw shop orange circles anymore

    // Only draw facilities if needed
    if (mapData.facilities)
    {
        Object.entries(mapData.facilities).forEach(
            ([facilityId, facility]) =>
            {
                createPOIMarker(
                    facilityId,
                    facility
                );
            }
        );
    }
}

// SHOP HOTSPOT
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

            let hotspot = null;

            // RECTANGLE SHOP
            if (shop.hotspot.type === "rect")
            {
                hotspot =
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
            }

            // POLYGON SHOP
            else if (shop.hotspot.type === "polygon")
            {
                hotspot =
                    document.createElementNS(
                        "http://www.w3.org/2000/svg",
                        "polygon"
                    );

                const points =
                    shop.hotspot.points
                        .map(point =>
                            `${point[0]},${point[1]}`
                        )
                        .join(" ");

                hotspot.setAttribute(
                    "points",
                    points
                );
            }

            // Invalid hotspot type
            if (!hotspot)
            {
                console.warn(
                    "Invalid hotspot:",
                    shopId
                );

                return;
            }

            hotspot.classList.add(
                "shop-hotspot"
            );

            hotspot.dataset.shopId =
                shopId;

            hotspot.addEventListener(
                "click",
                function()
                {
                    selectShop(shopId);
                }
            );

            hotspotGroup.appendChild(
                hotspot
            );
        }
    );
}

// SELECT SHOP
function selectShop(shopId)
{
    const mapShop =
        mapData.shop_locations[shopId];

    if (!mapShop)
    {
        console.error(
            "Shop not found:",
            shopId
        );

        return;
    }

    closeUtilityDetails();

    const dbShop = shopDatabase[shopId];

    // Prefer live database details (category, hours, description) once
    // connected; fall back to the map's own data so this still works
    // without a database.
    const shop = {
        name: (dbShop && dbShop.display_name) || mapShop.name,
        category: dbShop && dbShop.category,
        unit: dbShop && dbShop.unit,
        operatingHours: (dbShop && dbShop.operating_hours) || null,
        floor: (dbShop && dbShop.floor_name) || mapShop.floor,
        description: dbShop && dbShop.description,
    };

    selectedShopId = shopId;
    selectedUtilityId = null;
    selectedDestination = {
        label: shop.name,
        nodeId: mapShop.node_id
    };

    const shopSelect =
        document.getElementById("shop-select");

    shopSelect.value = shopId;

    const shopSearch =
        document.getElementById("shop-search");

    if (shopSearch)
    {
        shopSearch.value = shop.name;
    }

    hideShopSuggestions();

    updateSelectedShopPanel(
        shopId,
        shop
    );

    renderUtilityLocations();
    highlightSelectedShop(shopId);
    showShopDetails(shop);
}

function selectUtility(utilityId)
{
    const utility = mapData.facilities && mapData.facilities[utilityId];

    if (!utility)
    {
        return;
    }

    selectedShopId = null;
    selectedUtilityId = utilityId;
    selectedDestination = {
        label: utility.name,
        nodeId: utility.node_id
    };

    document.getElementById("shop-select").value = "";
    document.getElementById("selected-shop-details").textContent = "No shop selected";

    renderUtilityLocations();
    highlightSelectedShop(utilityId);
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
                shop.unit
                ? `<div>Unit: ${shop.unit}</div>`
                : ""
            }

            ${
                shop.floor
                ? `<div>${shop.floor}</div>`
                : ""
            }

            ${
                shop.operatingHours
                ? `<div>Hours: ${shop.operatingHours}</div>`
                : ""
            }

            ${
                shop.description
                ? `<div>${shop.description}</div>`
                : ""
            }

        </div>
    `;
}

// HIGHLIGHT SELECTED SHOP
function highlightSelectedShop(shopId)
{
    document
        .querySelectorAll(".shop-hotspot")
        .forEach(hotspot =>
        {
            hotspot.classList.remove(
                "selected"
            );
        });

    const selectedHotspot =
        document.querySelector(
            `.shop-hotspot[data-shop-id="${shopId}"]`
        );

    if (selectedHotspot)
    {
        selectedHotspot.classList.add(
            "selected"
        );
    }
}

// LOAD DATA STORED IN DB
async function loadShopDatabase()
{
    try
    {
        const response = await fetch("/api/shops");

        if (!response.ok)
        {
            throw new Error("Failed to load shop database.");
        }

        const shops = await response.json();

        console.log("Raw shop database:", shops);
        shopRecords = shops;

        shopDatabase = {};

        shops.forEach(shop =>
        {
            if (!shop.shop_code)
            {
                return;
            }

            // Normalise shop information
            const normalisedShop = {
                ...shop,

                display_name:
                    shop.shop_name ||
                    shop.name ||
                    shop.label ||
                    "Unnamed Shop"
            };

            shopDatabase[shop.shop_code] =
                normalisedShop;
        });

        console.log(
            "Normalised shop database:",
            shopDatabase
        );
    }
    catch (error)
    {
        // Expected until a real database is connected - the app still
        // works fine using data/map.json's own shop info as a fallback.
        console.warn(
            "Shop database unavailable, using map.json data instead:",
            error
        );
    }

    }

async function loadCategories() {
    try {
        const response = await fetch("/api/categories");

        if (!response.ok) {
            throw new Error("Failed to load categories.");
        }

        const categories = await response.json();
        categoryNames = Array.from(
            new Set(
                categories
                    .map(item => item.category && item.category.trim())
                    .filter(Boolean)
            )
        ).sort((firstCategory, secondCategory) =>
            firstCategory.localeCompare(secondCategory));
    }
    catch (error) {
        console.warn("Categories unavailable:", error);
        categoryNames = [];
    }
}
