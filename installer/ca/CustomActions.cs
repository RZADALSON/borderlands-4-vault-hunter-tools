using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Microsoft.Win32;
using WixToolset.Dtf.WindowsInstaller;

public static class CustomActions
{
    private const string GameExe = "Borderlands4.exe";
    private const string SteamAppId = "1285190";
    private const string SteamFolder = "Borderlands 4";

    /// <summary>Points INSTALLFOLDER at the game: where we installed last time, or wherever it's found.</summary>
    [CustomAction]
    public static ActionResult DetectGameFolder(Session session)
    {
        try
        {
            string saved = session["INSTALLFOLDER_SAVED"];
            if (!string.IsNullOrEmpty(saved))
            {
                session["INSTALLFOLDER"] = WithSlash(saved);
                return ActionResult.Success;
            }

            // Chosen in the dialog, or given on the command line. Never swap that for another folder,
            // if it's wrong it should be refused.
            if (!string.IsNullOrEmpty(session["INSTALLFOLDER"]))
            {
                return ActionResult.Success;
            }

            foreach (string candidate in Candidates(session))
            {
                if (IsGameFolder(candidate))
                {
                    session.Log("Found the game in " + candidate);
                    session["INSTALLFOLDER"] = WithSlash(candidate);
                    break;
                }
            }
        }
        catch (Exception ex)
        {
            // Not finding it is fine, the player can still point at it
            session.Log("Couldn't look for the game: " + ex);
        }
        return ActionResult.Success;
    }

    /// <summary>Checks the chosen folder from the dialog, for it to show GAME_FOLDER_ERROR.</summary>
    [CustomAction]
    public static ActionResult ValidateGameFolder(Session session)
    {
        string error = FolderProblem(session);
        session["GAME_FOLDER_OK"] = error == null ? "1" : "0";
        session["GAME_FOLDER_ERROR"] = error ?? "";
        return ActionResult.Success;
    }

    /// <summary>The same check for installs without dialogs, which stops them if it fails.</summary>
    [CustomAction]
    public static ActionResult ValidateGameFolderExecute(Session session)
    {
        string error = FolderProblem(session);
        if (error == null)
        {
            return ActionResult.Success;
        }
        session.Log("Refusing to install: " + error);
        var record = new Record(1);
        record[0] = "[1]";
        record[1] = error;
        session.Message(InstallMessage.Error, record);
        return ActionResult.Failure;
    }

    /// <summary>Installs the Visual C++ runtime the SDK needs, if it's missing or too old.</summary>
    [CustomAction]
    public static ActionResult InstallVcRedist(Session session)
    {
        // Runs after the install's transaction: the runtime's own installer couldn't start during it
        string path = null;
        try
        {
            int wantedMinor = int.Parse(session["VCREDIST_MINOR"]);
            if (HasVcRuntime(wantedMinor))
            {
                session.Log("The Visual C++ runtime is already installed.");
                return ActionResult.Success;
            }

            path = Path.Combine(Path.GetTempPath(), "BL4_vc_redist_" + Guid.NewGuid().ToString("N") + ".x64.exe");
            using (View view = session.Database.OpenView("SELECT `Data` FROM `Binary` WHERE `Name`='VcRedist'"))
            {
                view.Execute();
                using (Record record = view.Fetch())
                {
                    record.GetStream(1, path);
                }
            }

            var start = new ProcessStartInfo(path, "/install /passive /norestart") { UseShellExecute = true };
            using (Process process = Process.Start(start))
            {
                process.WaitForExit();
                session.Log("The Visual C++ runtime's installer returned " + process.ExitCode);
                // 3010: needs a restart, 1638: a newer one is there, 1641: restarting
                if (process.ExitCode != 0 && process.ExitCode != 3010 && process.ExitCode != 1638 && process.ExitCode != 1641)
                {
                    Warn(session, Say(session,
                        "Nie udało się zainstalować Microsoft Visual C++ Redistributable (kod " + process.ExitCode + "). Bez niego mody się nie uruchomią. Pobierz go ze strony Microsoftu: https://aka.ms/vs/17/release/vc_redist.x64.exe",
                        "Couldn't install the Microsoft Visual C++ Redistributable (code " + process.ExitCode + "). The mods won't start without it. Get it from Microsoft: https://aka.ms/vs/17/release/vc_redist.x64.exe"));
                }
            }
        }
        catch (Exception ex)
        {
            session.Log("Couldn't install the Visual C++ runtime: " + ex);
            Warn(session, Say(session,
                "Nie udało się zainstalować Microsoft Visual C++ Redistributable. Bez niego mody się nie uruchomią. Pobierz go ze strony Microsoftu: https://aka.ms/vs/17/release/vc_redist.x64.exe",
                "Couldn't install the Microsoft Visual C++ Redistributable. The mods won't start without it. Get it from Microsoft: https://aka.ms/vs/17/release/vc_redist.x64.exe"));
        }
        finally
        {
            try
            {
                if (path != null)
                {
                    File.Delete(path);
                }
            }
            catch (Exception)
            {
                // It's in the temp folder, not worth failing over
            }
        }
        return ActionResult.Success;
    }

    private static void Warn(Session session, string text)
    {
        var record = new Record(1);
        record[0] = "[1]";
        record[1] = text;
        session.Message(InstallMessage.Warning, record);
    }

    private static bool HasVcRuntime(int wantedMinor)
    {
        using (RegistryKey hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
        using (RegistryKey key = hklm.OpenSubKey(@"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"))
        {
            if (key == null || !(key.GetValue("Installed") is int installed) || installed != 1)
            {
                return false;
            }
            int major = key.GetValue("Major") is int m ? m : 0;
            int minor = key.GetValue("Minor") is int n ? n : 0;
            return major > 14 || (major == 14 && minor >= wantedMinor);
        }
    }

    private const string PolishLanguageId = "1045";

    /// <summary>Picks the text for the language this installer was built in.</summary>
    private static string Say(Session session, string polish, string english)
    {
        return session["ProductLanguage"] == PolishLanguageId ? polish : english;
    }

    private static string FolderProblem(Session session)
    {
        string folder = session["INSTALLFOLDER"];
        if (string.IsNullOrWhiteSpace(folder) || !IsGameFolder(folder))
        {
            return Say(session,
                "W tym folderze nie ma gry. Wybierz główny folder Borderlands 4, ten z plikiem " + GameExe + ".",
                "The game isn't in this folder. Choose the main Borderlands 4 folder, the one with " + GameExe + " in it.");
        }
        if (Process.GetProcessesByName(Path.GetFileNameWithoutExtension(GameExe)).Length > 0)
        {
            return Say(session,
                "Borderlands 4 jest uruchomione. Zamknij grę i spróbuj ponownie.",
                "Borderlands 4 is running. Close the game and try again.");
        }
        return null;
    }

    private static bool IsGameFolder(string folder)
    {
        try
        {
            return File.Exists(Path.Combine(folder, GameExe)) && Directory.Exists(Path.Combine(folder, "OakGame"));
        }
        catch (ArgumentException)
        {
            return false;
        }
    }

    private static string WithSlash(string folder)
    {
        return folder.EndsWith("\\") ? folder : folder + "\\";
    }

    private static IEnumerable<string> Candidates(Session session)
    {
        foreach (string library in SteamLibraries(session))
        {
            yield return Path.Combine(library, "steamapps", "common", SteamFolder);
        }

        string steamUninstall = ReadRegistry(
            RegistryHive.LocalMachine,
            @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App " + SteamAppId,
            "InstallLocation");
        if (steamUninstall != null)
        {
            yield return steamUninstall;
        }

        foreach (string location in EpicLocations(session))
        {
            yield return location;
        }
        yield return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Epic Games", "Borderlands 4");
    }

    private static IEnumerable<string> SteamLibraries(Session session)
    {
        var steamRoots = new List<string>
        {
            ReadRegistry(RegistryHive.LocalMachine, @"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            ReadRegistry(RegistryHive.CurrentUser, @"SOFTWARE\Valve\Steam", "SteamPath"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Steam"),
        };

        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string root in steamRoots.Where(r => !string.IsNullOrEmpty(r)))
        {
            if (seen.Add(root))
            {
                yield return root;
            }

            string vdf = Path.Combine(root, "steamapps", "libraryfolders.vdf");
            string text = null;
            try
            {
                text = File.Exists(vdf) ? File.ReadAllText(vdf) : null;
            }
            catch (Exception ex)
            {
                session.Log("Couldn't read " + vdf + ": " + ex.Message);
            }
            if (text == null)
            {
                continue;
            }

            foreach (Match match in Regex.Matches(text, "\"path\"\\s+\"([^\"]+)\""))
            {
                string library = match.Groups[1].Value.Replace("\\\\", "\\");
                if (seen.Add(library))
                {
                    yield return library;
                }
            }
        }
    }

    private static IEnumerable<string> EpicLocations(Session session)
    {
        string manifests = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "Epic", "EpicGamesLauncher", "Data", "Manifests");
        string[] files;
        try
        {
            files = Directory.Exists(manifests) ? Directory.GetFiles(manifests, "*.item") : new string[0];
        }
        catch (Exception ex)
        {
            session.Log("Couldn't read Epic's manifests: " + ex.Message);
            yield break;
        }

        foreach (string file in files)
        {
            string location = null;
            try
            {
                Match match = Regex.Match(File.ReadAllText(file), "\"InstallLocation\"\\s*:\\s*\"([^\"]+)\"");
                if (match.Success)
                {
                    location = match.Groups[1].Value.Replace("\\\\", "\\");
                }
            }
            catch (Exception ex)
            {
                session.Log("Couldn't read " + file + ": " + ex.Message);
            }
            if (location != null)
            {
                yield return location;
            }
        }
    }

    private static string ReadRegistry(RegistryHive hive, string path, string name)
    {
        try
        {
            using (RegistryKey root = RegistryKey.OpenBaseKey(hive, RegistryView.Registry64))
            using (RegistryKey key = root.OpenSubKey(path))
            {
                return key?.GetValue(name) as string;
            }
        }
        catch (Exception)
        {
            return null;
        }
    }
}
