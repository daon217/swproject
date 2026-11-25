const app = {
  ...consoleState,
  ...loginPage,
  ...consoleLayout,
  ...consoleCharts,
  ...crawlingPage,
  ...affiliatePage,
  ...customersPage,
  ...counselingPage,
  ...statsPage,
  ...dashboardPage,
};

window.addEventListener('DOMContentLoaded', () => {
  app.init();
});
