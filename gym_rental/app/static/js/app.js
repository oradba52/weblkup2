/* Small vanilla-JS interactions replacing jQuery, Bootstrap JS and AdminLTE JS. */
(() => {
  "use strict";
  document.addEventListener("click", (event) => {
    const menuButton = event.target.closest('[data-widget="pushmenu"]');
    if (menuButton) {
      event.preventDefault();
      document.body.classList.toggle("sidebar-open");
      return;
    }

    const dropdownToggle = event.target.closest('[data-toggle="dropdown"]');
    if (dropdownToggle) {
      event.preventDefault();
      const menu = dropdownToggle.parentElement.querySelector(".dropdown-menu");
      if (menu) menu.classList.toggle("show");
      return;
    }

    const dismiss = event.target.closest('[data-dismiss="alert"]');
    if (dismiss) {
      const alert = dismiss.closest(".alert");
      if (alert) alert.remove();
      return;
    }

    if (!event.target.closest(".dropdown-menu")) {
      document.querySelectorAll(".dropdown-menu.show").forEach((menu) => menu.classList.remove("show"));
    }
    if (window.matchMedia("(max-width: 767px)").matches &&
        !event.target.closest(".main-sidebar") &&
        !event.target.closest('[data-widget="pushmenu"]')) {
      document.body.classList.remove("sidebar-open");
    }
  });
})();
