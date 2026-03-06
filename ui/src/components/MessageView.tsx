import React from "react";
import { Box, Text } from "ink";
import { Separator } from "./Separator.js";
import { theme } from "../theme.js";
import { formatElapsed } from "../utils.js";
import type { ChatMessage, AppConfig } from "../types.js";

interface MessageViewProps {
  message: ChatMessage;
  config: AppConfig;
}

export const MessageView: React.FC<MessageViewProps> = ({
  message,
  config,
}) => {
  const isUser = message.role === "user";
  const name = isUser ? config.user_name : config.assistant_name;
  const nameColor = isUser ? theme.colors.user : theme.colors.assistant;

  return (
    <Box flexDirection="column">
      <Separator />
      <Text color={nameColor} bold>
        {name}
      </Text>
      <Box paddingLeft={0} flexDirection="column">
        <Text wrap="wrap">{message.content || "(empty)"}</Text>
      </Box>
      {message.elapsed !== undefined && message.elapsed > 0 && (
        <Text dimColor>{formatElapsed(message.elapsed)}</Text>
      )}
    </Box>
  );
};

interface StreamingMessageProps {
  name: string;
  content: string;
  elapsed?: number;
}

export const StreamingMessage: React.FC<StreamingMessageProps> = ({
  name,
  content,
  elapsed,
}) => {
  return (
    <Box flexDirection="column">
      <Separator />
      <Text color={theme.colors.assistant} bold>
        {name}
      </Text>
      <Box flexDirection="column">
        <Text wrap="wrap">{content || ""}</Text>
        {content && <Text color={theme.colors.primary}>▎</Text>}
      </Box>
      {elapsed !== undefined && elapsed > 0 && (
        <Text dimColor>{formatElapsed(elapsed)}</Text>
      )}
    </Box>
  );
};
