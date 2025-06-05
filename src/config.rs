use crate::gateway;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Eq, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(rename = "snake_case")]
pub enum SourceConfig {
    #[cfg(feature = "serialport")]
    Serial(SerialSourceConfig),
    Tcp(TcpConnectionConfig),
}

impl SourceConfig {
    pub fn open(&self) -> Result<Box<dyn gateway::physical::Connection>, std::io::Error> {
        match self {
            #[cfg(feature = "serialport")]
            SourceConfig::Serial(config) => {
                let conn = gateway::physical::serialport::Port::open(&config.name)?;
                Ok(Box::new(conn))
            }
            SourceConfig::Tcp(config) => {
                let addr = (config.hostname.as_str(), config.port);
                let readonly = match config.mode {
                    ConnectionMode::ReadWrite => false,
                    ConnectionMode::ReadOnly => true,
                };
                let keepalive = KeepaliveConfig {
                    idle: config.keepalive_idle, 
                    interval: config.keepalive_interval,
                    count: config.keepalive_count
                };

                let conn = gateway::physical::tcp::Connection::connect(addr, readonly, keepalive)?;
                Ok(Box::new(conn))
            }
        }
    }
}

#[derive(Debug, Clone, Eq, PartialEq, Serialize, Deserialize, JsonSchema)]
#[cfg(feature = "serialport")]
pub struct SerialSourceConfig {
    pub name: String,
}
impl From<SerialSourceConfig> for SourceConfig {
    fn from(value: SerialSourceConfig) -> Self {
        SourceConfig::Serial(value)
    }
}

#[derive(Debug, Clone, Eq, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct TcpConnectionConfig {
    pub hostname: String,
    #[serde(default = "default_port")]
    pub port: u16,
    pub mode: ConnectionMode,
    // Idle time before keepalive probes are sent.
    #[serde(default = "default_keepalive_idle")]
    pub keepalive_idle: std::time::Duration,
    /// Interval between individual keepalive probes.
    #[serde(default = "default_keepalive_interval")]
    pub keepalive_interval: std::time::Duration,
    /// Number of unacknowledged probes before the connection is considered dead.
    #[serde(default = "default_keepalive_count")]
    pub keepalive_count: u32,
}
impl From<TcpConnectionConfig> for SourceConfig {
    fn from(value: TcpConnectionConfig) -> Self {
        Self::Tcp(value)
    }
}

fn default_port() -> u16 {
    7160
}

fn default_default_keepalive_idle() -> std::time::Duration {
    30
}

fn default_default_keepalive_interval() -> std::time::Duration {
    10
}

fn default_default_keepalive_count() -> u32 {
    5
}


#[derive(Debug, Clone, Eq, PartialEq, Default, Serialize, Deserialize, JsonSchema)]
pub enum ConnectionMode {
    #[default]
    #[serde(rename = "readonly", alias = "ro")]
    ReadOnly,
    #[serde(rename = "readwrite", alias = "rw")]
    ReadWrite,
}
