{
  config,
  lib,
  ...
}: let
  cfg = config.services.slack-assistant;
in {
  options.services.slack-assistant = {
    enable = lib.mkEnableOption "FRC 447 Slack daily report";
    package = lib.mkOption {
      type = lib.types.package;
      description = "Packaged slack-assistant.";
    };
    user = lib.mkOption {
      type = lib.types.str;
      default = "dthompson";
    };
    environmentFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Env file with Slack, database, and model secrets.";
    };
    onCalendar = lib.mkOption {
      type = lib.types.str;
      default = "22:00:00";
    };
    timeZone = lib.mkOption {
      type = lib.types.str;
      default = "America/Indiana/Indianapolis";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.slack-assistant = {
      description = "FRC 447 Slack daily report";
      after = ["network-online.target" "postgresql.service"];
      wants = ["network-online.target"];
      environment.TZ = cfg.timeZone;
      serviceConfig =
        {
          Type = "oneshot";
          User = cfg.user;
          ExecStart = lib.getExe cfg.package;
        }
        // lib.optionalAttrs (cfg.environmentFile != null) {
          EnvironmentFile = cfg.environmentFile;
        };
    };

    systemd.timers.slack-assistant = {
      wantedBy = ["timers.target"];
      timerConfig = {
        OnCalendar = cfg.onCalendar;
        Persistent = true;
        Timezone = cfg.timeZone;
      };
    };
  };
}
