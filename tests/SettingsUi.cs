using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;

class SettingsUi {
    static IEnumerable<Control> Children(Control parent) {
        foreach(Control child in parent.Controls) {
            yield return child; foreach(var nested in Children(child)) yield return nested;
        }
    }
    [STAThread] static void Main(string[] args) {
        var home=Path.GetFullPath(args[1]);
        Environment.SetEnvironmentVariable("MAILPILOT_HOME",home);
        string target=Path.Combine(home,"自定义 索引");
        var assembly=Assembly.LoadFrom(Path.GetFullPath(args[0]));var type=assembly.GetType("MailPilot.Options",true);
        var fields=type.GetField("fields",BindingFlags.NonPublic|BindingFlags.Instance);
        Application.EnableVisualStyles();
        using(var form=(Form)Activator.CreateInstance(type,true)) {
            form.Show();Application.DoEvents();
            ((Dictionary<string,Control>)fields.GetValue(form))["indexDir"].Text=target;
            Children(form).OfType<Button>().Single(b=>b.Text=="保存").PerformClick();
            Application.DoEvents();
            if(!Directory.Exists(target) || form.DialogResult!=DialogResult.OK)throw new Exception("Settings not saved");
        }
        using(var form=(Form)Activator.CreateInstance(type,true)) {
            if(((Dictionary<string,Control>)fields.GetValue(form))["indexDir"].Text!=target)throw new Exception("Settings not restored");
        }
        Console.WriteLine("PASS custom index path saved through Settings and restored on reopen");
    }
}
