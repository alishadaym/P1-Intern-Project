let mapData = null;
const DEFAULT_FLOOR_ID = "2f";
const DEFAULT_START_NODE = "2f_node_lift_east";
const FLOOR_IDS = ["ground", "upper-ground", "2f"];
const FLOOR_TRANSFER_DISTANCE = 100;
const LIFT_LANES = [
    ["ground_lift_centre", "ug_lift_centre", "2f_lift_north"],
    ["ground_lift_south", "ug_lift_north", "2f_lift_west"],
    ["ground_lift_east", "ug_lift_south", "2f_lift_east"]
];
let currentFloorId = DEFAULT_FLOOR_ID;
let routeStartNodeOverride = null;
let selectedShopId = null;
let shopDatabase = {};
let shopRecords = [];
let categoryNames = [];
let selectedDestination = null;
let lastShopTrigger = null;
let utilityRecords = [];
let selectedUtilityId = null;
let activeUtilityId = null;
let utilityRefreshInProgress = false;
let activeShopId = null;
let utilityMapZoom = 1;
let utilityMapPanX = 0;
let utilityMapPanY = 0;
let utilityMapDragStartX = 0;
let utilityMapDragStartY = 0;
let utilityMapDragStartPanX = 0;
let utilityMapDragStartPanY = 0;
let utilityMapDragging = false;

function getStartNodeId()
{
    const startNodeData = document.getElementById("start-node-data");
    const scannedStartNodeId = startNodeData
        ? JSON.parse(startNodeData.textContent)
        : null;

    if (routeStartNodeOverride && mapData && mapData.nodes[routeStartNodeOverride])
    {
        return routeStartNodeOverride;
    }

    if (scannedStartNodeId && mapData && mapData.nodes[scannedStartNodeId])
    {
        return scannedStartNodeId;
    }

    const entranceNode = mapData.entrances
        .map(entrance => entrance.node_id)
        .find(nodeId => mapData.nodes[nodeId]);
    if (entranceNode)
    {
        return entranceNode;
    }

    const facilityNode = Object.values(mapData.facilities || {})
        .map(facility => facility.node_id)
        .find(nodeId => mapData.nodes[nodeId]);
    if (facilityNode)
    {
        return facilityNode;
    }

    return Object.keys(mapData.nodes)[0] || null;
}

// LOAD MAP DATA FROM FLASK
async function loadMapData(floorId = currentFloorId)
{
    document.getElementById("shop-hotspots").innerHTML = "";
    document.getElementById("poi-markers").innerHTML = "";

    try
    {
        const response = await fetch(`/api/map?floor=${encodeURIComponent(floorId)}`);

        if (!response.ok)
        {
            throw new Error("Failed to load map data.");
        }

        mapData = await response.json();
        currentFloorId = floorId;

        const floorMap = document.getElementById("floor-map");
        floorMap.src = `/static/img/${mapData.image.filename}`;
        floorMap.alt = mapData.name;

        const overlay = document.getElementById("map-overlay");

        overlay.setAttribute("viewBox", `0 0 ${mapData.image.width} ${mapData.image.height}`);

        drawNavigationNetwork();
        drawUserMarker();
        await loadUtilitiesSafely();
        drawPOIMarkers();
        drawShopHotspots();
    }
    catch (error)
    {
        console.error("Error loading map:", error);
    }
}

// LOAD UTILITIES (never throws - a failure here shouldn't break the
// rest of the page; the map just won't show restroom/lift markers)
async function loadUtilitiesSafely()
{
    try
    {
        await loadUtilities();
    }
    catch (error)
    {
        console.error("Error loading utilities:", error);
        mapData.facilities = {};
    }
}

// DRAW NAVIGATION NETWORK
function drawNavigationNetwork()
{
    const nodesGroup = document.getElementById("navigation-nodes");
    const linesGroup = document.getElementById("navigation-lines");

    // clear previous drawings
    nodesGroup.innerHTML = "";
    linesGroup.innerHTML = "";

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

        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");

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
            const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");

            circle.setAttribute("cx", node.x);
            circle.setAttribute("cy", node.y);

            circle.setAttribute("r", "6");
            circle.classList.add("navigation-node");

            nodesGroup.appendChild(circle);

            // NODE LABEL
            const label = document.createElementNS("http://www.w3.org/2000/svg", "text");

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
    document.getElementById("floor-select").value = DEFAULT_FLOOR_ID;
    await loadMapData();
    await loadShopDatabase();
    await loadCategories();
    populateShopDropdown();
    populateCategoryDropdown();
    checkShopFromURL();

    document.getElementById("floor-select").addEventListener("change", async function(event)
    {
        routeStartNodeOverride = null;
        stopNavigation();
        closeShopDetails();
        closeUtilityDetails();
        selectedShopId = null;
        selectedDestination = null;
        await loadMapData(event.target.value);
        populateShopDropdown();
        renderCategoryShops();
    });

    // NAVIGATE BUTTON
    const navigateButton = document.getElementById("navigate-btn");

    if (navigateButton)
    {
        navigateButton.addEventListener("click", toggleNavigation);
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

    // SHOP DETAILS MODAL
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

    // Occupancy can change server-side without a page reload
    window.setInterval(refreshUtilityData, 5000);

    // MAP ZOOM/PAN
    const mapContainer = document.querySelector(".map-container");
    const mapViewport = document.getElementById("map-viewport");
    mapContainer.addEventListener("pointerdown", startUtilityMapPan);
    mapContainer.addEventListener("pointermove", moveUtilityMapPan);
    mapContainer.addEventListener("pointerup", endUtilityMapPan);
    mapContainer.addEventListener("pointercancel", endUtilityMapPan);
    mapViewport.addEventListener("wheel", zoomMapWithWheel, { passive: false });
    document.getElementById("zoom-in-btn").addEventListener("click", () => changeMapZoom(0.25));
    document.getElementById("zoom-out-btn").addEventListener("click", () => changeMapZoom(-0.25));
    document.getElementById("zoom-reset-btn").addEventListener("click", closeUtilityDetails);
});

function setNavigationButtonState(isNavigating)
{
    const navigateButton = document.getElementById("navigate-btn");

    navigateButton.textContent = isNavigating
        ? "Stop Navigation"
        : "Navigate";
    navigateButton.classList.toggle("stop-navigation", isNavigating);
}

function toggleNavigation()
{
    const routeLine = document.getElementById("route-line");

    if (routeLine.getAttribute("points"))
    {
        stopNavigation();
        return;
    }

    startNavigation();
}

function stopNavigation()
{
    document.getElementById("route-line").setAttribute("points", "");
    setNavigationButtonState(false);
}

// DRAW USER CURRENT LOCATION
function drawUserMarker()
{
    const userMarker = document.getElementById("user-marker");

    // Set by the last scanned QR code; falls back to Main Entrance for guests
    const startNodeId = getStartNodeId();
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

// SHOP DROPDOWN (hidden - always holds every shop, kept in sync with
// whichever shop is currently selected)
function populateShopDropdown()
{
    const shopSelect = document.getElementById("shop-select");

    shopSelect.innerHTML = `<option value="">Select a shop</option>`;

    Object.keys(mapData.shop_locations).forEach(
        shopId =>
        {
            const option = document.createElement("option");

            option.value = shopId;
            option.textContent = getShopLabel(shopId);

            shopSelect.appendChild(option);
        }
    );
}

// CATEGORY FILTER
function populateCategoryDropdown() {
    const categorySelect = document.getElementById("category-select");
    categorySelect.innerHTML = "<option value=\"\">Select a category</option>";

    categoryNames
        .forEach(category => {
            const option = document.createElement("option");
            option.value = category;
            option.textContent = category;
            categorySelect.appendChild(option);
        });

    const utilitiesOption = document.createElement("option");
    utilitiesOption.value = "utilities";
    utilitiesOption.textContent = "Utilities";
    categorySelect.appendChild(utilitiesOption);
}

function renderCategoryShops() {
    const category = document.getElementById("category-select").value;
    const shopList = document.getElementById("category-shop-list");
    const resultsTitle = document.getElementById("category-results-title");

    if (category === "utilities") {
        resultsTitle.textContent = "Utilities";
        renderUtilityLocations();
        return;
    }

    resultsTitle.textContent = "Shops in Category";

    if (!category) {
        shopList.textContent = "Select a category to see shops or utilities";
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
        shopButton.classList.toggle(
            "selected",
            shop.shop_code === selectedShopId
        );
        shopButton.textContent = shop.shop_name || "Unnamed Shop";

        shopButton.addEventListener("click", () => selectShop(shop.shop_code));

        shopList.appendChild(shopButton);
    });
}

// SHOP SEARCH SUGGESTIONS
let activeSuggestionIndex = -1;

function renderShopSuggestions(searchText)
{
    const shopSuggestions = document.getElementById("shop-suggestions");

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
    const shopSuggestions = document.getElementById("shop-suggestions");

    shopSuggestions.classList.remove("visible");
    activeSuggestionIndex = -1;
}

function chooseShop(shopId, label)
{
    const shopSearch = document.getElementById("shop-search");

    shopSearch.value = label;
    hideShopSuggestions();
    selectShop(shopId);
}

function handleShopSearchKeydown(event)
{
    const shopSuggestions = document.getElementById("shop-suggestions");

    const items = Array.from(shopSuggestions.querySelectorAll("li:not(.no-results)"));

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

            const currentPosition = mapData.nodes[currentNode];
            const neighbourPosition = mapData.nodes[neighbour];

            // Euclidean distance
            const dx = neighbourPosition.x - currentPosition.x;
            const dy = neighbourPosition.y - currentPosition.y;

            const edgeDistance = Math.sqrt((dx * dx) + (dy * dy));

            const newDistance = distances[currentNode] + edgeDistance;

            if (newDistance < distances[neighbour])
            {
                distances[neighbour] = newDistance;
                previous[neighbour] = currentNode;
            }
        });
    }

    // No route found
    if (distances[endNodeId] === Infinity)
    {
        console.error("No route found between", startNodeId, "and", endNodeId);
        return null;
    }

    // Reconstruct route
    const path = [];
    let currentNode = endNodeId;

    while (currentNode !== null)
    {
        path.unshift(currentNode);
        currentNode = previous[currentNode];
    }

    if (path[0] !== startNodeId)
    {
        console.error("Route reconstruction failed.");
        return null;
    }

    return path;
}

function getPathDistance(path)
{
    let distance = 0;

    for (let index = 1; index < path.length; index += 1)
    {
        const previousNode = mapData.nodes[path[index - 1]];
        const currentNode = mapData.nodes[path[index]];
        const dx = currentNode.x - previousNode.x;
        const dy = currentNode.y - previousNode.y;
        distance += Math.sqrt((dx * dx) + (dy * dy));
    }

    return distance;
}

function findShortestPathInMap(floorMap, startNodeId, endNodeId)
{
    if (!floorMap.nodes[startNodeId] || !floorMap.nodes[endNodeId])
    {
        return null;
    }

    const distances = {};
    const previous = {};
    const unvisited = new Set(Object.keys(floorMap.nodes));

    Object.keys(floorMap.nodes).forEach(nodeId =>
    {
        distances[nodeId] = Infinity;
        previous[nodeId] = null;
    });
    distances[startNodeId] = 0;

    while (unvisited.size > 0)
    {
        let currentNode = null;
        let smallestDistance = Infinity;

        unvisited.forEach(nodeId =>
        {
            if (distances[nodeId] < smallestDistance)
            {
                smallestDistance = distances[nodeId];
                currentNode = nodeId;
            }
        });

        if (currentNode === null)
        {
            break;
        }

        unvisited.delete(currentNode);
        if (currentNode === endNodeId)
        {
            break;
        }

        floorMap.connections.forEach(connection =>
        {
            const [nodeA, nodeB] = connection;
            const neighbour = nodeA === currentNode
                ? nodeB
                : nodeB === currentNode ? nodeA : null;

            if (!neighbour || !unvisited.has(neighbour))
            {
                return;
            }

            const currentPosition = floorMap.nodes[currentNode];
            const neighbourPosition = floorMap.nodes[neighbour];
            const dx = neighbourPosition.x - currentPosition.x;
            const dy = neighbourPosition.y - currentPosition.y;
            const newDistance = distances[currentNode] + Math.sqrt((dx * dx) + (dy * dy));

            if (newDistance < distances[neighbour])
            {
                distances[neighbour] = newDistance;
                previous[neighbour] = currentNode;
            }
        });
    }

    if (distances[endNodeId] === Infinity)
    {
        return null;
    }

    const path = [];
    let currentNode = endNodeId;
    while (currentNode !== null)
    {
        path.unshift(currentNode);
        currentNode = previous[currentNode];
    }

    return path[0] === startNodeId ? path : null;
}

function getPathDistanceInMap(floorMap, path)
{
    let distance = 0;

    for (let index = 1; index < path.length; index += 1)
    {
        const previousNode = floorMap.nodes[path[index - 1]];
        const currentNode = floorMap.nodes[path[index]];
        distance += Math.hypot(
            currentNode.x - previousNode.x,
            currentNode.y - previousNode.y
        );
    }

    return distance;
}

async function loadFloorRoutingData()
{
    const floorData = await Promise.all(FLOOR_IDS.map(async floorId =>
    {
        const mapResponse = await fetch(`/api/map?floor=${encodeURIComponent(floorId)}`);
        const utilityResponse = await fetch(`/api/utilities?floor=${encodeURIComponent(floorId)}`);

        if (!mapResponse.ok || !utilityResponse.ok)
        {
            throw new Error(`Failed to load routing data for ${floorId}.`);
        }

        return {
            floorId,
            map: await mapResponse.json(),
            utilities: await utilityResponse.json()
        };
    }));

    return Object.fromEntries(floorData.map(item => [item.floorId, item]));
}

function getLiftUtilities(floorData)
{
    return floorData.utilities.filter(utility =>
        utility.type === "lift" && floorData.map.nodes[utility.node_id]
    );
}

function getMatchingDestinationLift(startLift, destinationFloorId, floorData)
{
    const liftLane = LIFT_LANES.find(lane => lane.includes(startLift.utility_code));
    if (!liftLane)
    {
        return null;
    }

    const destinationIndex = FLOOR_IDS.indexOf(destinationFloorId);
    const destinationUtilityCode = liftLane[destinationIndex];
    return getLiftUtilities(floorData).find(utility =>
        utility.utility_code === destinationUtilityCode
    ) || null;
}

async function findNearestRestroom()
{
    const startFloorId = currentFloorId;
    const startNodeId = getStartNodeId();

    if (!mapData.nodes[startNodeId])
    {
        alert("Your current location is not available on this floor.");
        return;
    }

    try
    {
        const floors = await loadFloorRoutingData();
        const startFloor = floors[startFloorId];
        const startLifts = getLiftUtilities(startFloor);
        let nearest = null;

        FLOOR_IDS.forEach(floorId =>
        {
            const destinationFloor = floors[floorId];
            const restrooms = destinationFloor.utilities.filter(utility =>
                utility.type === "restroom" && destinationFloor.map.nodes[utility.node_id]
            );

            restrooms.forEach(restroom =>
            {
                if (floorId === startFloorId)
                {
                    const path = findShortestPathInMap(startFloor.map, startNodeId, restroom.node_id);
                    if (path)
                    {
                        const distance = getPathDistanceInMap(startFloor.map, path);
                        if (!nearest || distance < nearest.distance)
                        {
                            nearest = { floorId, restroom, path, distance };
                        }
                    }
                    return;
                }

                startLifts.forEach(startLift =>
                {
                    const toLiftPath = findShortestPathInMap(startFloor.map, startNodeId, startLift.node_id);
                    const destinationLift = getMatchingDestinationLift(startLift, floorId, destinationFloor);

                    if (destinationLift)
                    {
                        const fromLiftPath = findShortestPathInMap(
                            destinationFloor.map,
                            destinationLift.node_id,
                            restroom.node_id
                        );
                        if (!toLiftPath || !fromLiftPath)
                        {
                            return;
                        }

                        const distance =
                            getPathDistanceInMap(startFloor.map, toLiftPath) +
                            FLOOR_TRANSFER_DISTANCE +
                            getPathDistanceInMap(destinationFloor.map, fromLiftPath);
                        if (!nearest || distance < nearest.distance)
                        {
                            nearest = {
                                floorId,
                                restroom,
                                path: fromLiftPath,
                                distance,
                                transferLift: startLift,
                                destinationLift
                            };
                        }
                    }
                });
            });
        });

        if (!nearest)
        {
            alert("No reachable restroom was found on any floor.");
            return;
        }

        if (nearest.floorId !== startFloorId)
        {
            routeStartNodeOverride = nearest.destinationLift.node_id;
            document.getElementById("floor-select").value = nearest.floorId;
            await loadMapData(nearest.floorId);
            populateShopDropdown();
        }

        selectUtility(nearest.restroom.utility_code);
        showUtilityDetails(nearest.restroom);
        startNavigation();
    }
    catch (error)
    {
        console.error("Error finding nearest restroom:", error);
        alert("The nearest restroom could not be calculated right now.");
    }
}

// DRAW ROUTE ON MAP
function drawRoute(path)
{
    const routeLine = document.getElementById("route-line");

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
    setNavigationButtonState(true);
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
        console.error("Destination node not found:", selectedDestination.nodeId);
        return;
    }

    const startNodeId = getStartNodeId();
    const destinationNodeId = selectedDestination.nodeId;

    const path = findShortestPath(startNodeId, destinationNodeId);

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

    const marker = document.createElementNS("http://www.w3.org/2000/svg", "circle");

    marker.setAttribute("cx", poi.x);
    marker.setAttribute("cy", poi.y);
    marker.setAttribute("r", "10");

    marker.classList.add("poi-marker");
    if (mapData.facilities && mapData.facilities[poiId])
    {
        marker.classList.add("utility-marker");
        if (String(poiId) === String(activeUtilityId))
        {
            marker.classList.add("utility-selected");
        }
    }

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
                selectUtility(poiId);
                // Pass the clicked marker directly so the orange highlight
                // is guaranteed to land on the exact element the user
                // clicked, instead of re-querying the DOM for it.
                showUtilityDetails(mapData.facilities[poiId], marker);
            }
        }
    );

    poiGroup.appendChild(marker);
}

function drawPOIMarkers()
{
    const poiGroup = document.getElementById("poi-markers");

    poiGroup.innerHTML = "";

    // Only draw facilities (restrooms/lifts/etc.) - shops no longer get
    // orange circle markers, just their hotspots.
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

// SHOP HOTSPOT
function drawShopHotspots()
{
    const hotspotGroup = document.getElementById("shop-hotspots");

    hotspotGroup.innerHTML = "";

    Object.entries(mapData.shop_locations).forEach(
        ([shopId, shop]) =>
        {
            if (!shop.hotspot)
            {
                return;
            }

            let hotspot = null;

            if (shop.hotspot.type === "polygon")
            {
                hotspot = document.createElementNS("http://www.w3.org/2000/svg", "polygon");

                const points = shop.hotspot.points
                    .map(point => `${point[0]},${point[1]}`)
                    .join(" ");

                hotspot.setAttribute("points", points);
            }
            else
            {
                // RECTANGLE SHOP (default - covers both the explicit
                // "rect" type and older entries with no "type" field at all)
                hotspot = document.createElementNS("http://www.w3.org/2000/svg", "rect");

                hotspot.setAttribute("x", shop.hotspot.x);
                hotspot.setAttribute("y", shop.hotspot.y);
                hotspot.setAttribute("width", shop.hotspot.width);
                hotspot.setAttribute("height", shop.hotspot.height);
            }

            if (!hotspot)
            {
                console.warn("Invalid hotspot:", shopId);
                return;
            }

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
function getFloorIdFromShop(shop)
{
    const floorCodes = {
        G: "ground",
        UG: "upper-ground",
        "2F": "2f"
    };

    const floorCode = shop && shop.floor_code
        ? shop.floor_code.trim().toUpperCase()
        : "";

    return floorCode
        ? floorCodes[floorCode] || currentFloorId
        : currentFloorId;
}

async function selectShop(shopId)
{
    const dbShop = shopDatabase[shopId];
    const targetFloorId = getFloorIdFromShop(dbShop);

    if (targetFloorId !== currentFloorId)
    {
        await loadMapData(targetFloorId);
        populateShopDropdown();
        renderCategoryShops();
    }

    document.getElementById("floor-select").value = targetFloorId;

    const mapShop = mapData.shop_locations[shopId];

    if (!mapShop)
    {
        console.error("Shop not found:", shopId);
        return;
    }

    const shouldUpdateActiveRoute = Boolean(
        document.getElementById("route-line").getAttribute("points")
    );
    closeUtilityDetails(false);

    // Prefer live database details (category, hours, description) once
    // connected; fall back to the map's own data so this still works
    // without a database.
    const shop = {
        mapId: shopId,
        x: mapShop.x,
        y: mapShop.y,
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

    const shopSelect = document.getElementById("shop-select");
    shopSelect.value = shopId;

    const shopSearch = document.getElementById("shop-search");
    if (shopSearch)
    {
        shopSearch.value = shop.name;
    }

    hideShopSuggestions();

    renderCategoryShops();
    highlightSelectedShop(shopId);
    showShopDetails(shop);

    if (shouldUpdateActiveRoute)
    {
        startNavigation();
    }
}

// SHOP DETAILS MODAL
function closeShopDetails()
{
    const shopModal = document.getElementById("shop-modal");
    shopModal.hidden = true;
    activeShopId = null;
    highlightSelectedShop(null);
    resetUtilityMapZoom();

    if (lastShopTrigger)
    {
        lastShopTrigger.focus();
        lastShopTrigger = null;
    }
}

function showShopDetails(shop)
{
    const shopModal = document.getElementById("shop-modal");
    const mapPoint = getShopMapPoint(shop.mapId);

    activeShopId = shop.mapId;
    lastShopTrigger = document.activeElement;
    document.getElementById("modal-shop-name").textContent = shop.name || "Unnamed Shop";
    document.getElementById("modal-shop-category").textContent = shop.category || "";
    document.getElementById("modal-shop-unit").textContent = shop.unit ? `Unit: ${shop.unit}` : "";
    document.getElementById("modal-shop-floor").textContent = shop.floor || "";
    document.getElementById("modal-shop-hours").textContent = shop.operatingHours ? `Hours: ${shop.operatingHours}` : "";
    document.getElementById("modal-shop-description").textContent = shop.description || "";

    // Zoom in on a fresh click; if the user is already zoomed in further,
    // keep their current zoom level instead of snapping back to 2x.
    utilityMapZoom = utilityMapZoom > 1 ? utilityMapZoom : 2;
    utilityMapPanX = 0;
    utilityMapPanY = 0;
    centerMapOnUtility(mapPoint);
    applyUtilityMapTransform();
    document.querySelector(".map-container").classList.add("map-zoomed");
    shopModal.hidden = false;
    positionMapPopover("shop-modal", `.shop-hotspot[data-shop-id="${shop.mapId}"]`);
    document.getElementById("close-shop-modal").focus();
}

function getShopMapPoint(shopId)
{
    const mapShop = mapData.shop_locations[shopId];

    if (Number.isFinite(mapShop.x) && Number.isFinite(mapShop.y))
    {
        return mapShop;
    }

    const hotspot = document.querySelector(`.shop-hotspot[data-shop-id="${shopId}"]`);
    const bounds = hotspot.getBBox();

    return {
        x: bounds.x + bounds.width / 2,
        y: bounds.y + bounds.height / 2
    };
}

// UTILITY DETAILS MODAL (toilets/lifts/baby care rooms)
function closeUtilityDetails(resetZoom = true)
{
    document.getElementById("utility-modal").hidden = true;
    activeUtilityId = null;
    clearSelectedUtilityMarker();
    if (resetZoom)
    {
        resetUtilityMapZoom();
    }
}

function showUtilityDetails(utility, markerElement)
{
    const utilityModal = document.getElementById("utility-modal");
    const mapContainer = document.querySelector(".map-container");
    activeUtilityId = utility.utility_code;
    setSelectedUtilityMarker(activeUtilityId, markerElement);

    // Clicking the marker directly should make this the nav target too,
    // same as picking it from the sidebar utility list
    selectedShopId = null;
    selectedUtilityId = utility.utility_code;
    selectedDestination = {
        label: utility.name,
        nodeId: utility.node_id
    };

    updateUtilityModal(utility);
    utilityMapZoom = utilityMapZoom > 1 ? utilityMapZoom : 2;
    utilityMapPanX = 0;
    utilityMapPanY = 0;
    centerMapOnUtility(utility);
    applyUtilityMapTransform();
    mapContainer.classList.add("utility-zoomed");
    utilityModal.hidden = false;
    positionUtilityModal(utility.utility_code);
    document.getElementById("close-utility-modal").focus();
}

function updateUtilityModal(utility)
{
    const status = getUtilityStatusLabel(utility);

    document.getElementById("modal-utility-name").textContent = utility.name;
    document.getElementById("modal-utility-floor").textContent = `Floor: ${utility.floor}`;
    document.getElementById("modal-utility-status").textContent = status
        ? status
        : "Available";
}

function positionUtilityModal(utilityId)
{
    positionMapPopover("utility-modal", `#poi-markers circle[data-poi-id="${utilityId}"]`);
}

function positionMapPopover(modalId, markerSelector)
{
    requestAnimationFrame(function()
    {
        const modal = document.getElementById(modalId);
        const modalContent = modal.querySelector(".utility-modal-content");
        const viewportBounds = document.getElementById("map-viewport").getBoundingClientRect();
        const marker = document.querySelector(markerSelector);

        if (!marker)
        {
            return;
        }

        const markerBounds = marker.getBoundingClientRect();
        const contentBounds = modalContent.getBoundingClientRect();
        const margin = 12;
        let left = markerBounds.right + margin;
        let top = markerBounds.top + (markerBounds.height - contentBounds.height) / 2;

        modalContent.classList.remove("left");
        if (left + contentBounds.width > viewportBounds.right - margin)
        {
            left = markerBounds.left - contentBounds.width - margin;
            modalContent.classList.add("left");
        }

        left = Math.max(
            viewportBounds.left + margin,
            Math.min(left, viewportBounds.right - contentBounds.width - margin)
        );
        top = Math.max(
            viewportBounds.top + margin,
            Math.min(top, viewportBounds.bottom - contentBounds.height - margin)
        );

        modalContent.style.left = `${left}px`;
        modalContent.style.top = `${top}px`;
    });
}

function resetUtilityMapZoom()
{
    const mapContainer = document.querySelector(".map-container");

    if (mapContainer)
    {
        utilityMapZoom = 1;
        utilityMapPanX = 0;
        utilityMapPanY = 0;
        mapContainer.style.transform = "";
        mapContainer.classList.remove("utility-zoomed");
        mapContainer.classList.remove("map-zoomed");
    }
}

function applyUtilityMapTransform()
{
    const mapContainer = document.querySelector(".map-container");

    if (mapContainer)
    {
        mapContainer.classList.toggle("map-zoomed", utilityMapZoom > 1);
        mapContainer.style.transform =
            `translate(${utilityMapPanX}px, ${utilityMapPanY}px) scale(${utilityMapZoom})`;
    }
}

function clampMapPan()
{
    const mapViewport = document.getElementById("map-viewport");
    const maximumPanX = mapViewport.clientWidth * (utilityMapZoom - 1) / 2;
    const maximumPanY = mapViewport.clientHeight * (utilityMapZoom - 1) / 2;

    utilityMapPanX = Math.max(-maximumPanX, Math.min(maximumPanX, utilityMapPanX));
    utilityMapPanY = Math.max(-maximumPanY, Math.min(maximumPanY, utilityMapPanY));
}

function centerMapOnUtility(utility)
{
    const mapViewport = document.getElementById("map-viewport");
    const baseX = utility.x / mapData.image.width * mapViewport.clientWidth;
    const baseY = utility.y / mapData.image.height * mapViewport.clientHeight;

    utilityMapPanX = mapViewport.clientWidth / 2 -
        (mapViewport.clientWidth / 2 + (baseX - mapViewport.clientWidth / 2) * utilityMapZoom);
    utilityMapPanY = mapViewport.clientHeight / 2 -
        (mapViewport.clientHeight / 2 + (baseY - mapViewport.clientHeight / 2) * utilityMapZoom);
    clampMapPan();
}

function changeMapZoom(amount)
{
    const nextZoom = Math.max(1, Math.min(4, utilityMapZoom + amount));
    if (nextZoom === utilityMapZoom)
    {
        return;
    }

    utilityMapZoom = nextZoom;
    clampMapPan();
    applyUtilityMapTransform();
    if (activeUtilityId)
    {
        positionUtilityModal(activeUtilityId);
    }
    if (activeShopId)
    {
        positionMapPopover("shop-modal", `.shop-hotspot[data-shop-id="${activeShopId}"]`);
    }
}

function zoomMapWithWheel(event)
{
    event.preventDefault();
    changeMapZoom(event.deltaY < 0 ? 0.25 : -0.25);
}

function startUtilityMapPan(event)
{
    const mapContainer = document.querySelector(".map-container");

    // Don't start a drag when zoomed out, or when the click is actually on
    // a shop hotspot / POI marker (those need to register as clicks, not
    // the start of a pan).
    if (
        utilityMapZoom <= 1
        || event.target.closest(".shop-hotspot, .poi-marker")
    )
    {
        return;
    }

    utilityMapDragging = true;
    utilityMapDragStartX = event.clientX;
    utilityMapDragStartY = event.clientY;
    utilityMapDragStartPanX = utilityMapPanX;
    utilityMapDragStartPanY = utilityMapPanY;
    mapContainer.classList.add("dragging");
    mapContainer.setPointerCapture(event.pointerId);
}

function moveUtilityMapPan(event)
{
    if (!utilityMapDragging)
    {
        return;
    }

    const mapContainer = document.querySelector(".map-container");
    utilityMapPanX = utilityMapDragStartPanX + event.clientX - utilityMapDragStartX;
    utilityMapPanY = utilityMapDragStartPanY + event.clientY - utilityMapDragStartY;
    clampMapPan();
    applyUtilityMapTransform();
    if (activeUtilityId)
    {
        positionUtilityModal(activeUtilityId);
    }
    if (activeShopId)
    {
        positionMapPopover("shop-modal", `.shop-hotspot[data-shop-id="${activeShopId}"]`);
    }
}

function endUtilityMapPan(event)
{
    if (!utilityMapDragging)
    {
        return;
    }

    const mapContainer = document.querySelector(".map-container");
    utilityMapDragging = false;
    mapContainer.classList.remove("dragging");

    if (event.pointerId !== undefined && mapContainer.hasPointerCapture(event.pointerId))
    {
        mapContainer.releasePointerCapture(event.pointerId);
    }
}

function getUtilityStatusLabel(utility)
{
    if (utility.type === "restroom" || utility.type === "baby_diaper")
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
    if (document.getElementById("category-select").value !== "utilities")
    {
        return;
    }

    const utilityType = "all";
    const utilityList = document.getElementById("category-shop-list");

    utilityList.innerHTML = "";

    if (!utilityType)
    {
        return;
    }

    const startNodeId = getStartNodeId();
    const matchingUtilities = Object.entries(mapData.facilities || {})
        .filter(([, utility]) => utilityType === "all" || utility.type === utilityType)
        .sort(([, firstUtility], [, secondUtility]) => {
            const typeOrder = {
                restroom: 1,
                baby_diaper: 2,
                oku: 3,
                lift: 4,
            };
            const typeDifference =
                (typeOrder[firstUtility.type] || 99) - (typeOrder[secondUtility.type] || 99);

            if (typeDifference === 0 && firstUtility.type === "restroom")
            {
                const firstPath = mapData.nodes[startNodeId] && mapData.nodes[firstUtility.node_id]
                    ? findShortestPath(startNodeId, firstUtility.node_id)
                    : null;
                const secondPath = mapData.nodes[startNodeId] && mapData.nodes[secondUtility.node_id]
                    ? findShortestPath(startNodeId, secondUtility.node_id)
                    : null;
                const firstDistance = firstPath ? getPathDistance(firstPath) : Infinity;
                const secondDistance = secondPath ? getPathDistance(secondPath) : Infinity;

                if (firstDistance !== secondDistance)
                {
                    return firstDistance - secondDistance;
                }
            }

            return typeDifference || (firstUtility.name || "").localeCompare(secondUtility.name || "");
        });

    if (matchingUtilities.length === 0)
    {
        utilityList.textContent = "No locations found";
        return;
    }

    const typeLabels = {
        restroom: "Restrooms",
        baby_diaper: "Baby Diaper Rooms",
        oku: "OKU Accessible Toilets",
        lift: "Lifts",
    };
    let previousType = null;

    matchingUtilities.forEach(([utilityId, utility]) =>
    {
        if (utilityType === "all" && utility.type !== previousType)
        {
            const heading = document.createElement("h4");
            heading.className = "utility-category-heading";
            heading.textContent = typeLabels[utility.type] || utility.type;
            utilityList.appendChild(heading);
            previousType = utility.type;
        }

        const utilityButton = document.createElement("button");
        const statusLabel = getUtilityStatusLabel(utility);
        const locationLabel = statusLabel
            ? `${utility.floor} - ${statusLabel}`
            : utility.floor;

        utilityButton.type = "button";
        utilityButton.className = "utility-list-item";
        utilityButton.dataset.utilityId = utilityId;
        utilityButton.textContent = utility.name;
        if (utilityId === selectedUtilityId)
        {
            utilityButton.classList.add("selected");
        }

        const status = document.createElement("span");
        status.className = "utility-status";
        status.textContent = locationLabel;
        utilityButton.appendChild(status);
        utilityButton.addEventListener("click", function()
        {
            selectUtility(utilityId);
            showUtilityDetails(utility);
        });

        utilityList.appendChild(utilityButton);
    });
}

function setSelectedUtilityMarker(utilityId, markerElement)
{
    clearSelectedUtilityMarker();
    const marker = markerElement
        || document.querySelector(`#poi-markers circle[data-poi-id="${utilityId}"]`);

    if (marker)
    {
        marker.classList.add("utility-selected");
    }
}

function clearSelectedUtilityMarker()
{
    document
        .querySelectorAll("#poi-markers circle.utility-selected")
        .forEach(marker => marker.classList.remove("utility-selected"));
}

function selectUtility(utilityId)
{
    const utility = mapData.facilities && mapData.facilities[utilityId];

    if (!utility)
    {
        return;
    }

    const shouldUpdateActiveRoute = Boolean(
        document.getElementById("route-line").getAttribute("points")
    );
    const shopModal = document.getElementById("shop-modal");
    if (!shopModal.hidden)
    {
        shopModal.hidden = true;
        activeShopId = null;
        highlightSelectedShop(null);
    }

    selectedShopId = null;
    selectedUtilityId = utilityId;
    selectedDestination = {
        label: utility.name,
        nodeId: utility.node_id
    };

    document.getElementById("shop-select").value = "";

    renderUtilityLocations();
    highlightSelectedShop(utilityId);

    if (shouldUpdateActiveRoute)
    {
        startNavigation();
    }
}

// HIGHLIGHT SELECTED SHOP
function highlightSelectedShop(shopId)
{
    document
        .querySelectorAll(".shop-hotspot")
        .forEach(hotspot =>
        {
            hotspot.classList.remove("selected");
        });

    const selectedHotspot = document.querySelector(`.shop-hotspot[data-shop-id="${shopId}"]`);

    if (selectedHotspot)
    {
        selectedHotspot.classList.add("selected");
    }
}

// LOAD UTILITIES (toilets/lifts/baby care rooms) FROM THE DB
async function loadUtilities()
{
    const response = await fetch(`/api/utilities?floor=${encodeURIComponent(currentFloorId)}`);

    if (!response.ok)
    {
        throw new Error("Failed to load utilities.");
    }

    utilityRecords = await response.json();
    mapData.facilities = Object.fromEntries(
        utilityRecords.map(utility => [utility.utility_code, utility])
    );
}

// Occupancy can change without a page reload, so poll for updates
async function refreshUtilityData()
{
    if (utilityRefreshInProgress)
    {
        return;
    }

    utilityRefreshInProgress = true;

    try
    {
        await loadUtilities();
        drawPOIMarkers();

        const categorySelect = document.getElementById("category-select");
        if (categorySelect.value === "utilities")
        {
            renderUtilityLocations();
        }

        if (activeUtilityId)
        {
            const utility = mapData.facilities[activeUtilityId];
            if (utility)
            {
                updateUtilityModal(utility);
                positionUtilityModal(activeUtilityId);
            }
            else
            {
                closeUtilityDetails();
            }
        }
    }
    catch (error)
    {
        console.error("Error refreshing utilities:", error);
    }
    finally
    {
        utilityRefreshInProgress = false;
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

            shopDatabase[shop.shop_code] = normalisedShop;
        });
    }
    catch (error)
    {
        // Expected until a real database is connected - the app still
        // works fine using data/map.json's own shop info as a fallback.
        console.warn("Shop database unavailable, using map.json data instead:", error);
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

function checkShopFromURL() {
    const params = new URLSearchParams(window.location.search);

    const shopId = params.get("shop");
    const shouldNavigate = params.get("navigate");

    if (params.get("nearest") === "1") {
        findNearestRestroom();
        return;
    }

    if (!shopId) {
        return;
    }

    // Make sure shop exists
    if (!mapData.shop_locations[shopId]) {
        console.error("Shop from URL not found:", shopId);
        return;
    }

    // Select the shop
    selectShop(shopId);

    // Automatically draw route
    if (shouldNavigate === "1") {
        startNavigation();
    }
}
