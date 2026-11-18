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
  ...consoleBackend,
};

window.addEventListener('DOMContentLoaded', () => {
  app.init();
});
