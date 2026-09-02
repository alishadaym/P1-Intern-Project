document.addEventListener("DOMContentLoaded", function () {

    const menuToggle = document.getElementById("menu-toggle");
    const sideMenu = document.getElementById("side-menu");
    const menuClose = document.getElementById("menu-close");

    if (menuToggle && sideMenu) {
        menuToggle.addEventListener("click", function () {
            sideMenu.classList.add("open");
        });
    }

    if (menuClose && sideMenu) {
        menuClose.addEventListener("click", function () {
            sideMenu.classList.remove("open");
        });
    }

});