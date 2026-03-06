import React from "react";
import { Box, Text } from "ink";
import { weatherEmoji } from "../utils.js";
import type { ContextInfo } from "../types.js";

interface ContextBarProps {
  context: ContextInfo;
}

export const ContextBar: React.FC<ContextBarProps> = ({ context }) => {
  const parts: React.ReactNode[] = [];

  if (context.date) {
    parts.push(
      <Text key="date" dimColor>
        📅 {context.date}
      </Text>
    );
  }
  if (context.location) {
    parts.push(
      <Text key="loc" dimColor>
        📍 {context.location}
      </Text>
    );
  }
  if (context.weather) {
    const emoji = weatherEmoji(context.weather_desc ?? "");
    parts.push(
      <Text key="weather" dimColor>
        {emoji} {context.weather}
      </Text>
    );
  }

  if (parts.length === 0) return null;

  return (
    <Box flexDirection="column" marginBottom={1}>
      {parts.map((p, i) => (
        <Box key={i} paddingLeft={2}>
          {p}
        </Box>
      ))}
    </Box>
  );
};
