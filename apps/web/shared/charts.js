const consoleCharts = {
  createCommonLineChartOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false, // 커스텀 범례 사용
        },
        tooltip: {
          mode: 'index',
          intersect: false,
        },
      },
      scales: {
        x: {
          grid: {
            color: '#f1f5f9',
          },
          ticks: {
            color: '#64748b',
            font: {
              family: 'Pretendard',
              size: 12,
            },
          },
        },
        y: {
          min: 0,
          max: 100,
          afterBuildTicks: (axis) => {
            axis.ticks = [{ value: 0 }, { value: 33 }, { value: 67 }, { value: 100 }];
          },
          grid: {
            color: '#f1f5f9',
          },
          ticks: {
            color: '#64748b',
            font: {
              family: 'Pretendard',
              size: 12,
            },
          },
        },
      },
    };
  },
};
