"use client";

import dynamic from "next/dynamic";
import { Box } from "@chakra-ui/react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

export interface PlotlySpec {
  data: Record<string, unknown>[];
  layout?: Record<string, unknown>;
}

interface ChartPanelProps {
  charts: PlotlySpec[];
}

const DEFAULT_LAYOUT: Record<string, unknown> = {
  autosize: true,
  height: 400,
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: {
    family: "system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif",
  },
};

const DEFAULT_CONFIG = {
  responsive: true,
  displayModeBar: true,
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d"],
};

export default function ChartPanel({ charts }: ChartPanelProps) {
  if (charts.length === 0) return null;

  return (
    <Box display="grid" gap={4} w="100%">
      {charts.map((chart, index) => (
        <Box
          key={index}
          bg="white"
          borderWidth="1px"
          borderColor="gray.200"
          borderRadius="md"
          p={4}
          overflow="hidden"
        >
          <Plot
            data={chart.data}
            layout={{ ...DEFAULT_LAYOUT, ...(chart.layout ?? {}) }}
            config={DEFAULT_CONFIG}
            useResizeHandler
            style={{ width: "100%", height: "400px" }}
          />
        </Box>
      ))}
    </Box>
  );
}
