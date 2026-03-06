import React, { useState, useEffect } from "react";
import { Box, Text } from "ink";
import { theme } from "../theme.js";
import { getTerminalWidth } from "../utils.js";

interface LoadingBarProps {
  loaded: number;
  total: number;
  label?: string;
}

export const LoadingBar: React.FC<LoadingBarProps> = ({
  loaded,
  total,
  label = "Loading...",
}) => {
  const [frameIdx, setFrameIdx] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setFrameIdx((i) => (i + 1) % theme.sparkleFrames.length);
    }, 100);
    return () => clearInterval(interval);
  }, []);

  const cols = getTerminalWidth();
  const barWidth = Math.min(30, cols - 30);

  if (total <= 0) {
    return (
      <Box>
        <Text color={theme.colors.warning}>{label}</Text>
        <Text color={theme.colors.primary}>
          {theme.sparkleFrames[frameIdx]}
        </Text>
      </Box>
    );
  }

  const pct = Math.min(loaded / total, 1.0);
  const filled = Math.round(barWidth * pct);
  const empty = barWidth - filled;

  return (
    <Box>
      <Text color={theme.colors.warning}>{label} </Text>
      <Text color={theme.colors.success}>{"━".repeat(filled)}</Text>
      <Text dimColor>{"─".repeat(empty)}</Text>
      <Text bold> {Math.round(pct * 100)}%</Text>
      <Text color={theme.colors.primary}>
        {theme.sparkleFrames[frameIdx]}
      </Text>
    </Box>
  );
};
