let selectedDirectoryShop = null;
let directoryShops = [];
let selectedCategory = "";
let selectedFloor = "";

document.addEventListener(
    "DOMContentLoaded",
    async function ()
    {
        await loadDirectoryShops();

        setupModal();
        setupMenu();
        setupDirectoryDropdowns();

        document
            .getElementById("directory-search")
            .addEventListener(
                "input",
                renderDirectoryShops
            );
    }
);

// LOAD SHOPS FROM DATABASE
async function loadDirectoryShops()
{
    try
    {
        const response =
            await fetch("/api/shops");

        if (!response.ok)
        {
            throw new Error("Unable to load shops.");
        }

        const shops =await response.json();

        // Keep only shops that have a shop_code
        directoryShops =
            shops.filter(shop => shop.shop_code);

        // Create category + floor dropdown options
        populateDirectoryFilters();

        // Display all shops initially
        renderDirectoryShops();
    }

    catch (error)
    {
        console.error(
            "Directory error:",
            error
        );
    }
}

// OPEN SHOP MODAL
function openShopModal(shop) {
    selectedDirectoryShop = shop;

    document.getElementById(
        "modal-shop-name"
    ).textContent =
        shop.shop_name || "Unnamed Shop";

    document.getElementById(
        "modal-category"
    ).textContent =
        shop.category
            ? `Category: ${shop.category}`
            : "";

    document.getElementById(
        "modal-unit"
    ).textContent =
        shop.unit
            ? `Unit: ${shop.unit}`
            : "";

    document.getElementById(
        "modal-floor"
    ).textContent =
        shop.floor_name || "";

    document.getElementById(
        "modal-hours"
    ).textContent =
        shop.operating_hours
            ? `Hours: ${shop.operating_hours}`
            : "";

    document.getElementById(
        "modal-description"
    ).textContent =
        shop.full_description ||
        "No description available.";

    document.getElementById(
        "modal-products"
    ).textContent =
        shop.products_services ||
        "Product information unavailable.";

    const websiteSection =
        document.getElementById(
            "website-section"
        );

    const websiteLink =
        document.getElementById(
            "modal-website"
        );

    if (shop.website_url) {
        websiteSection.style.display =
            "block";

        websiteLink.href =
            shop.website_url;
    }
    else {
        websiteSection.style.display =
            "none";
    }

    document.getElementById(
        "shop-modal"
    ).classList.add("show");
}

// MODAL
function setupModal() {
    const modal = document.getElementById(
            "shop-modal"
        );

    const closeButton = document.getElementById(
            "modal-close"
        );

    const goHereButton = document.getElementById(
            "go-here-btn"
        );

    closeButton.addEventListener("click", function () {
            modal.classList.remove(
                "show"
            );
        }
    );

    modal.addEventListener("click", function (event) {
            if (event.target === modal) {
                modal.classList.remove(
                    "show"
                );
            }
        }
    );

    // GO TO MAP
    goHereButton.addEventListener("click", function () {
            if (!selectedDirectoryShop) {
                return;
            }

            const shopCode = selectedDirectoryShop.shop_code;

            window.location.href = `/map?shop=${encodeURIComponent(shopCode)}&navigate=1`;
        }
    );
}

// MENU BUTTON
function setupMenu() {
    const menu = document.getElementById(
            "side-menu"
        );

    document.getElementById("menu-toggle").addEventListener(
        "click", function () {
            menu.classList.add("open");
        }
    );

    document.getElementById("menu-close").addEventListener(
        "click", function () {
            menu.classList.remove(
                "open"
            );
        }
    );
}

function populateDirectoryFilters()
{
    const categoryMenu = document.getElementById("category-menu");

    const floorMenu = document.getElementById("floor-menu");

    categoryMenu.innerHTML = "";
    floorMenu.innerHTML = "";

    /* ALL CATEGORIES */
    const allCategoryButton = document.createElement("button");

    allCategoryButton.type = "button";

    allCategoryButton.textContent = "All Categories";

    allCategoryButton.addEventListener(
        "click", function()
        {
            selectedCategory = "";

            document.getElementById(
                "category-label"
            ).textContent = "Filter Category";

            closeDropdowns();
            renderDirectoryShops();
        }
    );

    categoryMenu.appendChild(allCategoryButton);

    /* CATEGORY OPTIONS */
    const categories =
        [...new Set(directoryShops.map(shop => shop.category).filter(Boolean))].sort();

    categories.forEach(category =>
    {
        const button = document.createElement("button");

        button.type = "button";
        button.textContent = category;

        button.addEventListener(
            "click", function()
            {
                selectedCategory = category;

                document.getElementById("category-label").textContent = category;

                closeDropdowns();
                renderDirectoryShops();
            }
        );

        categoryMenu.appendChild(button);
    });

    /* ALL FLOORS */
    const allFloorButton = document.createElement("button");

    allFloorButton.type = "button";

    allFloorButton.textContent = "All Floors";

    allFloorButton.addEventListener(
        "click", function()
        {
            selectedFloor = "";

            document.getElementById("floor-label").textContent = "Choose Floor";

            closeDropdowns();
            renderDirectoryShops();
        }
    );

    floorMenu.appendChild(allFloorButton);

    /* FLOOR OPTIONS */
    const floors =
        [...new Set(directoryShops.map(shop => shop.floor_name).filter(Boolean))].sort();

    floors.forEach(floor =>
    {
        const button = document.createElement("button");

        button.type = "button";
        button.textContent = floor;

        button.addEventListener(
            "click", function()
            {
                selectedFloor =floor;

                document.getElementById("floor-label").textContent = floor;

                closeDropdowns();
                renderDirectoryShops();
            }
        );

        floorMenu.appendChild(
            button
        );
    });
}

function renderDirectoryShops()
{
    const searchText =
        document.getElementById("directory-search").value.trim().toLowerCase();

    const filteredShops =
        directoryShops.filter(shop =>
        {
            const name =
                (shop.shop_name || "").toLowerCase();

            const matchesSearch =
                !searchText || name.includes(searchText);

            const matchesCategory =
                !selectedCategory || shop.category === selectedCategory;

            const matchesFloor =
                !selectedFloor || shop.floor_name === selectedFloor;

            return (
                matchesSearch && matchesCategory && matchesFloor
            );
        });

    displayDirectoryShopButtons(filteredShops);
}

function displayDirectoryShopButtons(shops)
{
    const shopList =
        document.getElementById(
            "shop-list"
        );

    shopList.innerHTML = "";


    if (shops.length === 0)
    {
        shopList.innerHTML =
            `<p class="no-shops">
                No shops found.
            </p>`;

        return;
    }


    shops.forEach(shop =>
    {
        const button =
            document.createElement(
                "button"
            );

        button.type = "button";

        button.className =
            "shop-button";

        button.textContent =
            shop.shop_name ||
            "Unnamed Shop";


        button.addEventListener(
            "click",
            function()
            {
                openShopModal(shop);
            }
        );


        shopList.appendChild(button);
    });
}

function setupDirectoryDropdowns()
{
    const categoryToggle =
        document.getElementById(
            "category-toggle"
        );

    const categoryDropdown =
        document.getElementById(
            "category-dropdown"
        );


    const floorToggle =
        document.getElementById(
            "floor-toggle"
        );

    const floorDropdown =
        document.getElementById(
            "floor-dropdown"
        );


    categoryToggle.addEventListener(
        "click",
        function(event)
        {
            event.stopPropagation();

            floorDropdown.classList.remove(
                "open"
            );

            categoryDropdown.classList.toggle(
                "open"
            );
        }
    );


    floorToggle.addEventListener(
        "click",
        function(event)
        {
            event.stopPropagation();

            categoryDropdown.classList.remove(
                "open"
            );

            floorDropdown.classList.toggle(
                "open"
            );
        }
    );


    document.addEventListener(
        "click",
        function(event)
        {
            if (
                !event.target.closest(
                    ".custom-dropdown"
                )
            )
            {
                closeDropdowns();
            }
        }
    );
}


function closeDropdowns()
{
    document
        .querySelectorAll(
            ".custom-dropdown"
        )
        .forEach(dropdown =>
        {
            dropdown.classList.remove(
                "open"
            );
        });
}