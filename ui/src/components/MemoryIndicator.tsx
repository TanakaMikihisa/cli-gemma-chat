import React, { useState, useEffect } from "react";
import { Box, Text } from "ink";
import { theme } from "../theme.js";

interface MemoryIndicatorProps {
  active: boolean;
  done?: boolean;
}

export const MemoryIndicator: React.FC<MemoryIndicatorProps> = ({
  active,
  done = false,
}) => {
  const [frameIdx, setFrameIdx] = useState(0);

  useEffect(() => {
    if (!active) return;
    const interval = setInterval(() => {
      setFrameIdx((i) => (i + 1) % theme.sparkleFrames.length);
    }, 120);
    return () => clearInterval(interval);
  }, [active]);

  if (done) {
    return (
      <Box paddingLeft={2}>
        <Text color={theme.colors.dim}>
          {theme.symbols.diamond} Memory updated
        </Text>
      </Box>
    );
  }

  if (!active) return null;

  return (
    <Box paddingLeft={2}>
      <Text color={theme.colors.warning}>Organizing memory...</Text>
      <Text color={theme.colors.primary}>
        {theme.sparkleFrames[frameIdx]}
      </Text>
    </Box>
  );
};
