/**
 * app/(auth)/login.tsx — Écran de connexion
 */
import { useState } from "react";
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator, Alert,
} from "react-native";
import { router } from "expo-router";
import { useAuth } from "../../store/authStore";

export default function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!email || !password) return Alert.alert("Erreur", "Remplis tous les champs");
    setLoading(true);
    try {
      await login(email.trim().toLowerCase(), password);
      router.replace("/(app)/(tabs)/home");
    } catch (e: any) {
      Alert.alert("Connexion échouée", e?.detail ?? "Vérifie tes identifiants");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <View style={styles.inner}>
        <Text style={styles.logo}>NV</Text>
        <Text style={styles.title}>Connexion</Text>
        <Text style={styles.subtitle}>nanovia.ca</Text>

        <TextInput
          style={styles.input}
          placeholder="Email"
          placeholderTextColor="#555"
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
          autoCapitalize="none"
          autoComplete="email"
        />
        <TextInput
          style={styles.input}
          placeholder="Mot de passe"
          placeholderTextColor="#555"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="password"
        />

        <TouchableOpacity style={styles.button} onPress={handleLogin} disabled={loading}>
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>Se connecter</Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity onPress={() => router.push("/(auth)/register")}>
          <Text style={styles.link}>Pas de compte ? Créer un compte</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0A0A0F" },
  inner: { flex: 1, justifyContent: "center", padding: 28 },
  logo: { fontSize: 40, fontWeight: "800", color: "#7C3AED", textAlign: "center", marginBottom: 8 },
  title: { fontSize: 26, fontWeight: "700", color: "#FFFFFF", textAlign: "center" },
  subtitle: { fontSize: 14, color: "#666", textAlign: "center", marginBottom: 40 },
  input: {
    backgroundColor: "#1A1A2E", color: "#FFF", borderRadius: 12,
    padding: 16, marginBottom: 16, fontSize: 15,
    borderWidth: 1, borderColor: "#2A2A4A",
  },
  button: {
    backgroundColor: "#7C3AED", borderRadius: 12, padding: 16,
    alignItems: "center", marginTop: 8,
  },
  buttonText: { color: "#FFF", fontWeight: "700", fontSize: 16 },
  link: { color: "#7C3AED", textAlign: "center", marginTop: 20, fontSize: 14 },
});
