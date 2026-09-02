let selectedDirectoryShop = null;

document.addEventListener(
    "DOMContentLoaded",
    async function () {
        await loadDirectoryShops();

        setupModal();
        setupMenu();
    }
);

// LOAD SHOPS FROM DATABASE
async function loadDirectoryShops() {
    try {
        const response = await fetch("/api/shops");

        if (!response.ok) {
            throw new Error(
                "Unable to load shops."
            );
        }

        const shops = await response.json();

        const shopList =
            document.getElementById(
                "shop-list"
            );

        shopList.innerHTML = "";

        shops.forEach(shop => {
            // Ignore shops without shop_code
            if (!shop.shop_code) {
                return;
            }

            const button =
                document.createElement(
                    "button"
                );

            button.classList.add(
                "shop-button"
            );

            button.textContent =
                shop.shop_name;

            button.addEventListener(
                "click",
                function () {
                    openShopModal(shop);
                }
            );

            shopList.appendChild(
                button
            );
        });
    }

    catch (error) {
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