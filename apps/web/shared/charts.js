const consoleCharts = {
  computeDynamicYScale(seriesList = [], { isInteger = true } = {}) {
    const values = seriesList.flat().map((v) => Number(v) || 0);
    const maxVal = Math.max(0, ...values);

    if (isInteger) {
      if (maxVal <= 3) {
        return { min: 0, max: 4, stepSize: 1, precision: 0 };
      }
      if (maxVal <= 8) {
        const top = Math.ceil((maxVal + 1) / 2) * 2;
        return { min: 0, max: top, stepSize: top / 4, precision: 0 };
      }
      const rawStep = Math.ceil((maxVal * 1.2) / 4);
      const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
      const norm = rawStep / mag;
      const niceNorm = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
      const stepSize = niceNorm * mag;
      return { min: 0, max: stepSize * 4, stepSize, precision: 0 };
    }

    // 실수형(매출 추이 · 만원 단위)
    if (maxVal === 0) {
      return { min: 0, max: 4, stepSize: 1 };
    }
    if (maxVal <= 1.5) {
      return { min: 0, max: 2, stepSize: 0.5 };
    }
    if (maxVal <= 3.5) {
      return { min: 0, max: 4, stepSize: 1 };
    }
    const rawStep = (maxVal * 1.2) / 4;
    const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
    const norm = rawStep / mag;
    const niceNorm = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
    const stepSize = Number((niceNorm * mag).toPrecision(4));
    return { min: 0, max: Number((stepSize * 4).toPrecision(4)), stepSize };
  },

  createCommonLineChartOptions(seriesList = [], { isInteger = true } = {}) {
    const yScale = this.computeDynamicYScale(seriesList, { isInteger });
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
          min: yScale.min,
          max: yScale.max,
          grid: {
            color: '#f1f5f9',
          },
          ticks: {
            stepSize: yScale.stepSize,
            precision: yScale.precision,
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
