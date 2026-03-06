import React, { useState, useEffect } from "react";
import { Box, Text } from "ink";
import { theme } from "../theme.js";
import { formatElapsed } from "../utils.js";

interface ThinkingIndicatorProps {
  name: string;
  startTime: number;
}

export const ThinkingIndicator: React.FC<ThinkingIndicatorProps> = ({
  name,
  startTime,
}) => {
  const [frameIdx, setFrameIdx] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setFrameIdx((i) => (i + 1) % theme.sparkleFrames.length);
      setElapsed((Date.now() - startTime) / 1000);
    }, 120);
    return () => clearInterval(interval);
  }, [startTime]);

  return (
    <Box flexDirection="column">
      <Box>
        <Text color={theme.colors.assistant} bold>
          {name}
        </Text>
        <Text color={theme.colors.dim}> thinking...</Text>
        <Text color={theme.colors.primary}>
          {theme.sparkleFrames[frameIdx]}
        </Text>
      </Box>
      <Text dimColor>{formatElapsed(elapsed)}</Text>
    </Box>
  );
};
